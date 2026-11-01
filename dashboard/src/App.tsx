import { useEffect, useState } from "react";
import "./styles.css";
import { ClaimDetail } from "./ClaimDetail";
import { Instructions } from "./Instructions";
import { Queue } from "./Queue";

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => {
      setHash(window.location.hash);
    };
    window.addEventListener("hashchange", onChange);
    return () => {
      window.removeEventListener("hashchange", onChange);
    };
  }, []);
  return hash;
}

function view(hash: string) {
  const claim = /^#\/claims\/(.+)$/.exec(hash);
  if (claim) return <ClaimDetail claimId={claim[1]} />;
  if (hash === "#/instructions") return <Instructions />;
  return <Queue />;
}

export function App() {
  const hash = useHash();
  return (
    <div className="app">
      <header className="masthead">
        <div>
          <h1>UnderCover</h1>
          <span className="tagline">Travel insurance claims</span>
        </div>
        <nav>
          <a href="#/">Queue</a>
          <a href="#/instructions">Instructions</a>
        </nav>
      </header>
      <main>{view(hash)}</main>
    </div>
  );
}
