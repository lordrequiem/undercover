import { useEffect, useState } from "react";
import {
  type ClaimDetail as Claim,
  type Decision,
  fetchClaim,
  formatMoney,
  titleCase,
} from "./api";
import { StatusBadge } from "./StatusBadge";

function Facts({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <dl className="facts">
      <dt>Type</dt>
      <dd>{titleCase(claim.claim_type)}</dd>
      <dt>Submitted</dt>
      <dd>{claim.submitted_on}</dd>
      <dt>Incident</dt>
      <dd>
        {claim.incident_date}, {claim.incident_location}
      </dd>
    </dl>
  );
}

function Items({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <section className="panel">
      <h2>Items claimed</h2>
      <div className="items-grid">
        {claim.items.map((item) => (
          <ItemRow
            key={item.description}
            description={item.description}
            amount={item.amount}
          />
        ))}
        <span className="total">Total claimed</span>
        <span className="total amount mono">
          {formatMoney(claim.amount_claimed)}
        </span>
      </div>
    </section>
  );
}

function ItemRow({
  description,
  amount,
}: Readonly<{
  description: string;
  amount: number;
}>) {
  return (
    <>
      <span>{description}</span>
      <span className="amount mono">{formatMoney(amount)}</span>
    </>
  );
}

function Documents({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <section className="panel">
      <h2>Documents</h2>
      {claim.documents.map((doc) => (
        <div key={doc.name}>
          <p className="label">{doc.name}</p>
          <p className="muted">{doc.content}</p>
        </div>
      ))}
    </section>
  );
}

function PolicyAndCustomer({ claim }: Readonly<{ claim: Claim }>) {
  const { policy, plan, customer } = claim;
  return (
    <section className="panel">
      <h2>Policy and customer</h2>
      <dl className="facts">
        <dt>Policy</dt>
        <dd className="mono">{policy.policy_id}</dd>
        <dt>Plan</dt>
        <dd>{plan.name}</dd>
        <dt>Trip</dt>
        <dd>
          {policy.trip.destination}, {policy.trip.departs_on} to{" "}
          {policy.trip.returns_on}
        </dd>
        <dt>Deductible</dt>
        <dd className="mono">{formatMoney(plan.deductible)}</dd>
        <dt>Customer</dt>
        <dd>{customer.name}</dd>
      </dl>
      <h2 style={{ marginTop: "16px" }}>Claim history</h2>
      {customer.previous_claims.length === 0 ? (
        <p className="muted">No previous claims.</p>
      ) : (
        <ul className="steps">
          {customer.previous_claims.map((prev) => (
            <li key={prev.claim_id}>
              <span className="label">{titleCase(prev.claim_type)}</span>,{" "}
              {prev.filed_on}
              <div className="detail">
                {prev.summary} — {prev.outcome}, {formatMoney(prev.amount_paid)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DecisionPanel({ decision }: Readonly<{ decision: Decision }>) {
  return (
    <section className="panel">
      <h2>Decision</h2>
      <dl className="facts">
        <dt>Decision</dt>
        <dd className="decision-tag">{titleCase(decision.decision)}</dd>
        <dt>Payout</dt>
        <dd className="mono">{formatMoney(decision.payout)}</dd>
        <dt>Policy section</dt>
        <dd>{decision.policy_section}</dd>
      </dl>
      <p>{decision.reason}</p>
    </section>
  );
}

function Activity({ claim }: Readonly<{ claim: Claim }>) {
  const working = claim.state === "in_progress";
  if (claim.steps.length === 0 && !working) return null;
  return (
    <section className="panel">
      <h2>Activity</h2>
      {working && <p className="muted">Working on the claim.</p>}
      <ul className="steps">
        {claim.steps.map((step, index) => (
          <li key={index}>
            <span className="label">{step.label}</span>
            <div className="detail">{step.detail}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ClaimDetail({ claimId }: Readonly<{ claimId: string }>) {
  const [claim, setClaim] = useState<Claim | null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      const next = await fetchClaim(claimId);
      if (!active) return;
      setClaim(next);
      if (next.state === "in_progress")
        timer = setTimeout(() => void load(), 1000);
    };
    void load();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [claimId]);

  if (!claim) return <p className="muted">Loading the claim.</p>;

  return (
    <div>
      <a className="back" href="#/">
        Back to the queue
      </a>
      <section className="panel">
        <h2>
          <span className="claim-id">{claim.claim_id}</span>{" "}
          <StatusBadge state={claim.state} />
        </h2>
        <p>{claim.summary}</p>
        <Facts claim={claim} />
        <p style={{ marginTop: "12px" }}>{claim.story}</p>
      </section>
      <Items claim={claim} />
      <Documents claim={claim} />
      <PolicyAndCustomer claim={claim} />
      {claim.decision && <DecisionPanel decision={claim.decision} />}
      <Activity claim={claim} />
    </div>
  );
}
