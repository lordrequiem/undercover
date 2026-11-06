import {
  type ClaimState,
  type RunItemStatus,
  runItemLabel,
  stateLabel,
} from "./api";

export function StatusBadge({ state }: Readonly<{ state: ClaimState }>) {
  return <span className={`badge ${state}`}>{stateLabel(state)}</span>;
}

export function RunItemBadge({ status }: Readonly<{ status: RunItemStatus }>) {
  return <span className={`badge ${status}`}>{runItemLabel(status)}</span>;
}
