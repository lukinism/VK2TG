export function formatDate(value?: string | null): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("ru-RU");
}

export function formatBytes(value?: number | null): string {
  if (!value) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  const formatted = size >= 100 || index === 0 ? size.toFixed(0) : size.toFixed(1);
  return `${formatted} ${units[index]}`;
}

export function statusLabel(status: string): string {
  const mapping: Record<string, string> = {
    queued: "В очереди",
    success: "Успешно",
    error: "Ошибка",
    skipped: "Пропущено",
    partial: "Частично",
    completed: "Завершено",
    busy: "Занят",
    running: "Работает",
    idle: "Ожидает",
  };
  return mapping[status] ?? status;
}
