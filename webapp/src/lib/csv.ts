/**
 * Minimal RFC-4180 CSV serialization. A field is quoted iff it contains a comma,
 * a double-quote, CR, or LF; embedded quotes are doubled. Rows are joined with
 * CRLF (the RFC line terminator). Used by the /methodology CSV export.
 */

export function csvCell(value: string): string {
  if (/[",\r\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

/** Serialize a matrix of string cells (row 0 is typically the header). */
export function toCsv(rows: ReadonlyArray<ReadonlyArray<string>>): string {
  return rows.map((row) => row.map(csvCell).join(',')).join('\r\n')
}
