type IconName = "bell" | "search" | "filter" | "plus" | "arrow" | "chevron" | "clock" | "check" | "calendar" | "close";

const paths: Record<IconName, string> = {
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4",
  search: "M21 21l-4.5-4.5M19 10.5a8.5 8.5 0 1 1-17 0 8.5 8.5 0 0 1 17 0",
  filter: "M4 5h16l-6 7v6l-4 2v-8L4 5Z",
  plus: "M12 5v14M5 12h14",
  arrow: "M5 12h14m-5-5 5 5-5 5",
  chevron: "m7 10 5 5 5-5",
  clock: "M12 7v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  check: "m5 12 4 4L19 6",
  calendar: "M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z",
  close: "m6 6 12 12M6 18 18 6",
};

export function InterfaceIcon({ name }: { name: IconName }) {
  return <svg className="interface-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
