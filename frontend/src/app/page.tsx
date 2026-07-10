export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 px-8">
      <h1 className="font-display text-[34px] leading-[42px] font-semibold text-text">
        Wren
      </h1>
      <p className="max-w-md text-center text-[17px] leading-[26px] text-text-secondary">
        A private, branded AI support and sales agent for any business.
        Surfaces arrive in phase 1 (tenant resolution, T-005).
      </p>
      <span className="rounded-full bg-accent-subtle px-4 py-1 text-[13px] leading-[18px] font-medium text-accent-active">
        scaffold - phase 0
      </span>
    </main>
  );
}
