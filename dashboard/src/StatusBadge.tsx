import { type ClaimState, stateLabel } from "./api";

export function StatusBadge({ state }: Readonly<{ state: ClaimState }>) {
  return <span className={`badge ${state}`}>{stateLabel(state)}</span>;
}
