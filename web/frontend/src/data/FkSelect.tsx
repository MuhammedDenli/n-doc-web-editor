import { useLookup } from "../api/queries";
import type { Values } from "./rows";

interface Props {
  table: string;
  column: string;
  values: Values;
  /** Columns to set: the option's full (possibly composite) key. */
  onSelect: (key: Values) => void;
}

/** Select for a foreign key column; choosing a referenced row fills every
 * column of the foreign key. */
export function FkSelect({ table, column, values, onSelect }: Props) {
  const lookup = useLookup(table, column);
  const options = lookup.data ?? [];
  const id = (key: Values) => JSON.stringify(key);
  const current = options.find((o) => Object.entries(o.key).every(([c, v]) => values[c] === v));
  const raw = values[column] ?? "";

  return (
    <select
      aria-label={column}
      value={current ? id(current.key) : raw ? "unknown" : ""}
      disabled={lookup.isPending}
      onChange={(e) => {
        if (e.target.value === "") {
          const empty = Object.fromEntries(
            Object.keys(options[0]?.key ?? { [column]: "" }).map((c) => [c, ""]),
          );
          onSelect(empty);
          return;
        }
        const option = options.find((o) => id(o.key) === e.target.value);
        if (option) onSelect(option.key);
      }}
    >
      <option value="">—</option>
      {!current && raw && (
        <option value="unknown" disabled>
          {raw} (not found)
        </option>
      )}
      {options.map((o) => (
        <option key={id(o.key)} value={id(o.key)}>
          {Object.keys(o.key).length > 1 ? Object.values(o.key).join(" / ") : o.value}
          {o.name ? ` — ${o.name}` : ""}
        </option>
      ))}
    </select>
  );
}
