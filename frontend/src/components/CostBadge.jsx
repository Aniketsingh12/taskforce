// Format a cost so small-but-real amounts never render as "$0.0000", which
// reads as free. Below a hundredth of a cent we show "<$0.0001" instead.
function formatCost(cost) {
  if (cost >= 0.0001) return `$${cost.toFixed(4)}`;
  return "<$0.0001";
}

export default function CostBadge({ cost = 0, tokens = 0 }) {
  const free = !cost || cost === 0;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
        free ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300"
      }`}
      title={`${tokens} tokens`}
    >
      {free ? "FREE" : formatCost(cost)}
      <span className="text-edge">·</span>
      <span className="text-gray-400">{tokens} tok</span>
    </span>
  );
}
