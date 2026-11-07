# Revue du harness (phases 1 à 6)

Revue des commits `ffbd5f3` à `d3bfa91` (6 novembre), soit 30 fichiers, contre
[HARNESS.md](./HARNESS.md) et [CODE_STANDARDS.md](./CODE_STANDARDS.md). Les
changements non commités (`dashboard/src/Queue.*`, `styles.css`, notebooks) ne
sont pas couverts.

## 1. Verdict

Le harness fait ce que HARNESS.md demande et il est bien testé. Il reste
quatre problèmes de robustesse (section 3), qui touchent directement les
exigences « un claim ne bloque jamais le run » et « jamais décidé ou payé deux
fois ». Le code est correct mais répète beaucoup de plomberie HTTP et de
motifs SQL (section 4). Rien n'est grave, tout se corrige en peu de lignes.

## 2. Vérifications faites

| Contrôle | Résultat |
|---|---|
| `ruff format --check`, `ruff check` | OK |
| `pyright` | 0 erreur |
| `uv run python -m pytest -q` | 45 tests passés, couverture 98,5 % |
| `npm run check` | Bloqué à `uv run pytest` par une stratégie de contrôle d'application Windows (os error 4551). Ce n'est pas un bug du code. Utiliser `uv run python -m pytest`. |
| `check:ts` et e2e | Non exécutés dans cette revue |
| Appel d'un vrai modèle | Non fait |

Les exigences de HARNESS.md sont toutes couvertes par un test : to-do list
stockée et affichée, plafond du run, claim en échec qui n'arrête pas le run,
nouvel essai, échec deux fois laissé à un handler, contrôle des claims
manqués, pas de seconde décision.

## 3. Problèmes fonctionnels

### 3.1 Le contrôle des claims manqués ne contrôle rien de nouveau

[agent/main.py](../agent/main.py), `run_queue`, seconde boucle.
Elle ne reparcourt que `ordered`, la liste déjà planifiée. Un claim `waiting`
absent de cette liste ne serait jamais vu, alors que le commentaire annonce le
contraire.
Correction : relire `waiting_claims(limit)` avant de finir et traiter ce qui
reste.

### 3.2 Une panne du backend arrête quand même le run

`safe_work` attrape l'exception du worker, mais son `except` appelle
`add_step`, qui appelle le backend. Si le backend est la cause, l'exception
remonte et le run s'arrête. Les appels `decided`, `requeue` et `set_item` de la
boucle principale ne sont pas protégés non plus.
HARNESS.md exige qu'un claim en échec n'arrête jamais le run.
Correction : un seul `try/except` autour du traitement complet d'un claim
dans la boucle, qui ne fait pas d'appel réseau pour se rapporter lui-même.

### 3.3 `POST /api/claims/{id}/for_handler` n'a pas de garde

[backend/main.py](../backend/main.py), `hand_to_handler`.
Contrairement à `requeue_claim`, il écrase l'état de n'importe quel claim, y
compris un claim décidé ou en attente de sign-off.
Correction : renvoyer 409 si `decision` n'est pas `NULL`.

### 3.4 Les instructions modifiées ne sont jamais rechargées

[backend/db.py](../backend/db.py), `seed`, utilise `INSERT OR IGNORE`. Une base
existante garde les anciennes instructions après une modification de
`claim_instructions.md` ou `queue_instructions.md`. L'ancienne clé
`instructions` reste orpheline dans `settings`.
Correction : documenter le reseed dans STATUS.md, ou remplacer par
`INSERT OR REPLACE` pour les deux clés d'instructions.

### 3.5 Autres points fonctionnels

- **Dashboard, polling** ([Queue.tsx](../dashboard/src/Queue.tsx)). Le
  rafraîchissement ne continue que si un run existe et n'est pas fini. Si la
  page est ouverte avant le début d'un run, ou si un ancien run est terminé,
  le nouveau run n'apparaît qu'après rechargement. Une erreur réseau dans
  `load` laisse la page sur « Loading the queue. » sans message.
- **`pay_claim`** (préexistant, phase 2). Aucun contrôle que `amount` égale le
  payout décidé, et un second paiement écrase `paid` au lieu d'être refusé.
  C'est le point le plus proche de « jamais payé deux fois ».
- **`decide_claim`**. Le test `decision IS NULL` et l'`UPDATE` ne sont pas
  atomiques. Un `UPDATE ... WHERE decision IS NULL` avec contrôle de
  `rowcount` est plus sûr.
- **`DecisionIn.payout`** n'est pas validé : un payout négatif ou nul sur un
  approve est accepté.
- **`plan_order`** retrouve les ids par `text.find`, une recherche de
  sous-chaîne. `CLM-100` serait trouvé dans `CLM-1001`. Utiliser
  `re.findall(r"CLM-\d+", text)`.
- **`open_run`** (backend) a pour docstring « Open a run over the first
  `limit` waiting claims », mais il ne fait que stocker `limit`. La docstring
  est trompeuse.
- **Écart avec « l'agent organise son propre travail »**. `run_queue` est une
  boucle Python avec un seul appel au modèle pour l'ordre. La to-do list et les
  helpers sont pilotés par le code. STATUS.md le dit, mais
  [queue_instructions.md](../backend/queue_instructions.md) parle comme si
  l'agent tenait la liste lui-même.
- **`reasoning_effort`** passe à `None` dès que `MODEL_NAME` est défini. C'est
  cohérent avec « MODEL_NAME surcharge », mais ce n'est pas écrit.

## 4. Examen du code contre les bonnes pratiques

Légende : bon, à améliorer, à corriger.

| Principe | Note | Résumé |
|---|---|---|
| DRY | à corriger | Beaucoup de plomberie HTTP et de motifs SQL répétés |
| KISS | à améliorer | `run_queue` a deux boucles proches, `summarise` reparse des chaînes |
| YAGNI | à améliorer | `thread_id`, `run()`, étape « Read the instructions » |
| Responsabilité unique | bon, sauf `run_queue` | Fonctions courtes et bien nommées |
| Gestion des erreurs | à corriger | Voir 3.2 |
| Types | bon, sauf `dict` nus | TypeScript strict sans `any`, Python avec `dict` non typés |
| Commentaires | bon | Rares et utiles |
| Tests | bon, répétitifs | Aucun appel au modèle, mais beaucoup de répétition |

### 4.1 DRY (don't repeat yourself)

**[agent/main.py](../agent/main.py)**

1. **Le motif `with backend() as client: ...; raise_for_status()` est écrit
   environ 12 fois** (`get_claim`, `list_handbook_sections`,
   `read_handbook_section`, `submit_decision`, `instructions`, `start`,
   `add_step`, `fetch_detail`, `waiting_claims`, `open_run`, `write_plan`,
   `set_item`, `finish_run`, `requeue`, `hand_to_handler`). Un helper
   `call(method, path, **kwargs)` qui ouvre le client, lève l'erreur et
   renvoie le JSON supprime la majorité de ces lignes.
2. **`get_claim` et `fetch_detail` font le même GET.** L'outil devrait
   appeler `fetch_detail`.
3. **`start`, `requeue` et `hand_to_handler` sont identiques** : un POST sans
   corps sur `/api/claims/{id}/<action>`. Une seule fonction
   `post_claim(claim_id, action)` suffit.
4. **Les outils sont décrits deux fois** : dans `FRAMING` et dans
   [claim_instructions.md](../backend/claim_instructions.md). Si l'un change,
   l'autre ment. Garder la description des outils à un seul endroit.
5. **Les statuts sont des chaînes littérales** (`"in_progress"`, `"to_do"`,
   `"for_handler"`, `"waiting"`...) définies séparément dans le backend
   (`Literal`, SQL), l'agent et [api.ts](../dashboard/src/api.ts). Au minimum,
   des constantes dans l'agent.
6. **Dans `run_queue`, le motif « travailler, tester `decided`, mettre à jour
   l'item » apparaît dans les deux boucles.**

**[backend/main.py](../backend/main.py)**

7. **`company()` duplique `setting()`.** `company(conn)` est
   `json.loads(setting(conn, "company"))`. `setting` est de plus définie après
   son premier usage.
8. **`start_claim`, `requeue_claim` et `hand_to_handler` font le même
   `UPDATE claims SET state = ?`**, avec chacun son `commit()` et son
   `return claim_detail(...)`. Un helper `set_state(conn, claim_id, state)`
   les réduit à trois lignes.
9. **`fetch_run` imite `fetch_claim`** (SELECT, 404 si absent). Un helper
   générique `fetch_one(conn, table, key, value)` couvre les deux. À ne
   faire que s'il reste lisible.
10. **`commit()` suivi de `return claim_detail(...)` se répète** dans presque
    chaque endpoint de mutation.

**Tests ([test_agent.py](../agent/tests/test_agent.py))**

11. **`monkeypatch.setattr(main, "backend", lambda: TestClient(app))` est
    recopié dans presque chaque test**, et `TestClient(app)` est recréé
    partout. Une fixture `autouse` règle les deux.

**Dashboard**

12. **`STATE_LABELS` et `RUN_ITEM_LABELS`** ([api.ts](../dashboard/src/api.ts))
    sont deux tables presque identiques (`in_progress`, `for_handler`). Peu
    grave, mais à garder en tête si une troisième apparaît.

### 4.2 KISS (keep it stupidly simple)

1. **`run_queue` fait trop.** Elle ouvre le run, planifie, boucle, réessaie,
   gère le handler et résume. Une version plus simple : une fonction
   `work_with_retry(claim_id)` qui tente jusqu'à deux fois, puis une boucle
   unique. Cela retire la seconde boucle et rend le contrôle des claims
   manqués (3.1) naturel.
2. **`summarise` reparse des chaînes produites par `report`.**
   `report.split(": ", 1)[1].split(",")[0]` couple les deux fonctions par un
   format texte. Faire retourner un résultat structuré (`outcome`, ligne de
   texte) à `work_claim` évite ce parsing fragile.
3. **`plan_order` trie par position dans le texte** et complète avec ce qui
   manque. C'est compact mais cryptique (voir aussi la fragilité en 3.5). Une
   regex et une boucle sont plus lisibles.
4. **`list_claims` fait des requêtes `record()` dans une boucle** (deux par
   claim). Acceptable pour un pilote, à signaler si la file grossit.
5. **[handbook.py](../backend/handbook.py) relit et redécoupe les fichiers à
   chaque appel.** Un `functools.cache` sur `_sections` le simplifie et
   l'accélère sans changer le comportement.

### 4.3 YAGNI (you aren't gonna need it)

1. **`thread_id`** est passé à `create_agent` dans `config`, mais il n'y a pas
   de checkpointer : il ne sert à rien. Il impose aussi un argument à `run()`.
2. **`run()` n'est qu'un alias de `work_claim`.** Un seul nom suffit.
3. **L'étape « Read the instructions »** est enregistrée avant que le modèle
   ait lu quoi que ce soit : c'est une étape décorative.
4. **Le paramètre `kind="claim"` par défaut de `instructions()`** n'est pas
   utile, les deux appels le nomment.

### 4.4 Responsabilité unique et nommage

- **Bon** : les fonctions de l'agent sont courtes, avec une docstring d'une
  ligne, et les noms disent ce qu'elles font (`waiting_claims`, `write_plan`,
  `set_item`).
- **Bon** : [handbook.py](../backend/handbook.py) fait une chose et la fait
  bien.
- **À améliorer** : `agent/main.py` mélange outils du modèle, client HTTP,
  orchestration du run et choix du modèle dans un fichier de 300 lignes. Le
  découper en `tools.py`, `client.py` et `run.py` serait justifié si le
  harness continue de grandir (Week 2), pas avant.
- **À améliorer** : `hand_to_handler` existe dans l'agent et dans le backend
  avec le même nom, mais des rôles différents (client et endpoint). Ce n'est
  pas faux, mais ça gêne la lecture.

### 4.5 Gestion des erreurs

CODE_STANDARDS demande « avoid overly defensive code ». Le code respecte
l'esprit : un seul `except Exception`, dans `safe_work`, et c'est le bon
endroit. Le problème est l'inverse, c'est que ce `except` n'est pas assez
robuste (3.2).

### 4.6 Types

- TypeScript : mode strict, aucun `any`.
- Python : `fetch_detail` et `report` utilisent `dict` nu. Un `TypedDict` ou
  un modèle Pydantic pour le détail d'un claim améliorerait pyright et
  documenterait les clés (`decision`, `state`).

### 4.7 Tests

- **Bon** : aucun appel à un modèle, un `StubModel` scripté, tous les
  comportements de HARNESS.md couverts.
- **À améliorer** : le test « prompt drops the wording » vérifie seulement que
  deux chaînes sont absentes. C'est un garde-fou faible.
- **À améliorer** : répétition de l'installation (voir DRY, point 11).

### 4.8 Conformité à CODE_STANDARDS.md

| Règle | Conforme |
|---|---|
| 1. Simple | En grande partie, sauf `run_queue` |
| 2. Commentaires seulement si nécessaire | Oui |
| 3. Concis, sans emoji | Oui |
| 4. Pas de code trop défensif | Oui |
| 5. `uv run` | Oui |
| 6. TypeScript strict, pas de `any` | Oui |

## 5. Plan d'action proposé

Par ordre de priorité.

1. Garde 409 sur `for_handler` (3.3).
2. Rendre `safe_work` et le traitement d'un claim insensibles à une panne du
   backend (3.2).
3. Relire la file avant de finir pour un vrai contrôle des claims manqués
   (3.1).
4. Instructions : recharger au seed ou documenter le reseed (3.4).
5. Réduire la plomberie : helper `call`, `post_claim`, `set_state`,
   `setting` et `company` (4.1).
6. Simplifier `run_queue` avec `work_with_retry` et un résultat structuré à la
   place des chaînes parsées (4.2).
7. Supprimer `thread_id`, `run()` et l'étape décorative (4.3).
8. Fixture de test `autouse` pour le client backend (4.1, point 11).
9. Polling continu et gestion d'erreur dans `Queue.tsx` (3.5).
10. Garde-fous de paiement : montant et double paiement (3.5).

Les points 1 à 4 sont des correctifs de comportement. Les points 5 à 8 sont de
la simplification sans changement de comportement : les 45 tests doivent
rester verts.
