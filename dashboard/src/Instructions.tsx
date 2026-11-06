import { useEffect, useState } from "react";
import { type InstructionSet, fetchInstructions } from "./api";

export function Instructions() {
  const [text, setText] = useState<InstructionSet | null>(null);

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
        <>
          <h3>Running the queue</h3>
          <pre className="instructions">{text.queue}</pre>
          <h3>Working a claim</h3>
          <pre className="instructions">{text.claim}</pre>
        </>
      )}
    </section>
  );
}
