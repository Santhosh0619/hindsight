function relativeTime(date: Date, now: Date): string {
  const diffSeconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const abs = Math.abs(diffSeconds);

  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"],
    [60, "minute"],
    [24, "hour"],
    [7, "day"],
    [4.345, "week"],
    [12, "month"],
    [Number.POSITIVE_INFINITY, "year"],
  ];

  const value = diffSeconds;
  let divisor = 1;
  for (const [amount, unit] of units) {
    if (abs / divisor < amount) {
      return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(
        Math.round(value / divisor),
        unit
      );
    }
    divisor *= amount;
  }
  return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(0, "second");
}

export function Timestamp({ value }: { value: string | Date }): React.JSX.Element {
  const date = typeof value === "string" ? new Date(value) : value;

  return (
    <time
      dateTime={date.toISOString()}
      title={date.toLocaleString()}
      className="font-mono text-sm text-muted-foreground"
    >
      {relativeTime(date, new Date())}
    </time>
  );
}
