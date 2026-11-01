import { useEffect, useState } from "react";
import { fetchInstructions } from "./api";

export function Instructions() {
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    void fetchInstructions().then(setText);
  }, []);

  return (
    <section className="panel">
      <h2>Agent instructions</h2>
      <p className="muted">
        Read only. These are the instructions the agent works from.
      </p>
      {text === null ? (
        <p className="muted">Loading the instructions.</p>
      ) : (
        <pre className="instructions">{text}</pre>
      )}
    </section>
  );
}
