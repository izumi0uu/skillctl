export function GhostLoader({ mini }: { mini?: boolean }) {
  return (
    <div className={mini ? "ghost-loader mini" : "ghost-loader"}>
      <div className="gl-ghost">
        <div className="gl-red">
          <div className="gl-pupil" />
          <div className="gl-pupil1" />
          <div className="gl-eye" />
          <div className="gl-eye1" />
          <div className="gl-top0 gl-solid" />
          <div className="gl-top1 gl-solid" />
          <div className="gl-top2 gl-solid" />
          <div className="gl-top3 gl-solid" />
          <div className="gl-top4 gl-solid" />
          <div className="gl-st0 gl-solid" />
          <div className="gl-st1 gl-solid" />
          <div className="gl-st2 gl-solid" />
          <div className="gl-st3 gl-solid" />
          <div className="gl-st4 gl-solid" />
          <div className="gl-st5 gl-solid" />
          <div className="gl-an1 gl-flick0" />
          <div className="gl-an2 gl-flick1" />
          <div className="gl-an3 gl-flick1" />
          <div className="gl-an4 gl-flick1" />
          <div className="gl-an5 gl-flick1" />
          <div className="gl-an6 gl-flick0" />
          <div className="gl-an7 gl-flick0" />
          <div className="gl-an8 gl-flick0" />
          <div className="gl-an9 gl-flick1" />
          <div className="gl-an10 gl-flick1" />
          <div className="gl-an11 gl-flick0" />
          <div className="gl-an12 gl-flick0" />
          <div className="gl-an13 gl-flick0" />
          <div className="gl-an14" />
          <div className="gl-an15 gl-flick1" />
          <div className="gl-an16 gl-flick1" />
          <div className="gl-an17 gl-flick1" />
          <div className="gl-an18 gl-flick0" />
        </div>
        <div className="gl-shadow" />
      </div>
    </div>
  );
}

export function CoffeeLoader() {
  return (
    <div className="coffee-loader">
      <div className="cl-cup">
        <div className="cl-handle" />
        <div className="cl-smoke one" />
        <div className="cl-smoke two" />
        <div className="cl-smoke three" />
      </div>
      <div className="cl-load">..........................</div>
    </div>
  );
}
