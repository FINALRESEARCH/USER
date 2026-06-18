"use client";

import { useRef, useState } from "react";

function fmt(s: number): string {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

// Minimal player: play/pause, a 2px scrub bar, and time labels. No volume,
// mute, AirPlay, or download menu (the native controls can't drop those
// selectively, so we render our own and keep the <audio> element headless).
export default function AudioPlayer({ src }: { src: string }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);

  function toggle() {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) {
      a.play();
    } else {
      a.pause();
    }
  }

  function seek(e: React.ChangeEvent<HTMLInputElement>) {
    const a = audioRef.current;
    if (!a) return;
    const t = Number(e.target.value);
    a.currentTime = t;
    setCurrent(t);
  }

  const pct = duration > 0 ? (current / duration) * 100 : 0;

  return (
    <div className="player">
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
        onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
      />

      <button
        type="button"
        onClick={toggle}
        aria-label={playing ? "Pause" : "Play"}
      >
        {playing ? (
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <rect x="1" y="1" width="3.5" height="10" fill="currentColor" />
            <rect x="7.5" y="1" width="3.5" height="10" fill="currentColor" />
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M2 1 L11 6 L2 11 Z" fill="currentColor" />
          </svg>
        )}
      </button>

      <time>{fmt(current)}</time>

      <input
        type="range"
        min={0}
        max={duration || 0}
        step={0.1}
        value={current}
        onChange={seek}
        aria-label="Seek"
        style={{
          background: `linear-gradient(to right, #fff ${pct}%, #555 ${pct}%)`,
        }}
      />

      <time>{fmt(duration)}</time>
    </div>
  );
}
