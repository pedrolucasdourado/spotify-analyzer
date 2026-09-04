import { useEffect, useId, useMemo, useRef, useState } from "react";
import { int } from "../format";
import type { CountryOption } from "../types";

interface Props {
  countries: CountryOption[];
  value: string;
  onChange: (code: string) => void;
}

function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/** Combobox com busca: com dezenas de praças, uma fileira de botões não serve. */
export function CountryPicker({ countries, value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  const selected = countries.find((c) => c.code === value);

  const matches = useMemo(() => {
    const q = fold(query.trim());
    if (!q) return countries;
    return countries.filter((c) => fold(c.name).includes(q) || c.code.includes(q));
  }, [countries, query]);

  // fecha ao clicar fora
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  useEffect(() => {
    setCursor(0);
  }, [query]);

  // mantém a opção destacada visível
  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector<HTMLLIElement>(`[data-idx="${cursor}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [cursor, open]);

  function commit(code: string) {
    onChange(code);
    setOpen(false);
    setQuery("");
    inputRef.current?.blur();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const step = e.key === "ArrowDown" ? 1 : -1;
      setCursor((c) => (c + step + matches.length) % Math.max(1, matches.length));
    } else if (e.key === "Enter") {
      if (open && matches[cursor]) {
        e.preventDefault();
        commit(matches[cursor].code);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
    }
  }

  return (
    <div className="picker" ref={boxRef}>
      <span className="caption" id={`${listId}-label`}>
        Praça do evento
      </span>

      <div className="picker-field">
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-labelledby={`${listId}-label`}
          aria-autocomplete="list"
          aria-activedescendant={open && matches[cursor] ? `${listId}-${cursor}` : undefined}
          className="picker-input"
          value={open ? query : (selected?.name ?? value)}
          placeholder="Digite um país"
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => {
            setOpen(true);
            setQuery("");
          }}
          onKeyDown={onKeyDown}
        />
        <button
          type="button"
          className="picker-toggle"
          tabIndex={-1}
          aria-hidden="true"
          onClick={() => (open ? setOpen(false) : inputRef.current?.focus())}
        >
          ▾
        </button>
      </div>

      {open && (
        <ul className="picker-list" id={listId} role="listbox" ref={listRef}>
          {matches.length === 0 && <li className="picker-empty">Nenhuma praça com esse nome</li>}
          {matches.map((c, i) => (
            <li
              key={c.code}
              id={`${listId}-${i}`}
              data-idx={i}
              role="option"
              aria-selected={c.code === value}
              className={`picker-opt${i === cursor ? " cursor" : ""}${c.code === value ? " on" : ""}`}
              onMouseEnter={() => setCursor(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                commit(c.code);
              }}
            >
              <span className="picker-name">{c.name}</span>
              <span className="picker-code mono">{c.code.toUpperCase()}</span>
              <span className="picker-count mono">{int(c.active_artists)} ativos</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
