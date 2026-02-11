const motifs = [
  "Heritage Concierge",
  "Polki Intelligence",
  "Bridal Atelier",
  "Care Vault"
];

export function Hero() {
  return (
    <section className="glass-panel rounded-3xl px-10 py-12 mb-10">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="uppercase tracking-[0.3em] text-amber text-sm font-semibold">Jadau Admin Console</p>
          <h1 className="text-4xl lg:text-5xl font-display text-onyx mt-3">
            Shape every conversation like a bespoke couture experience
          </h1>
          <p className="text-onyx/70 mt-4 max-w-2xl">
            Curate AI prompts, fine-tune specialist pools, and train speech corrections so every caller feels they’re
            speaking with a seasoned jewelry concierge.
          </p>
        </div>
        <div className="flex gap-3 flex-wrap">
          {motifs.map((label) => (
            <div key={label} className="ribbon-tag bg-sand px-4 py-2 rounded-full text-xs font-medium text-onyx/80">
              {label}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
