import { useEffect, useRef, useState } from 'react';
import type { DashboardRow, SortOption } from './sortRows';
import styles from './FilterMenu.module.css';

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'default', label: 'Padrão' },
  { value: 'name-asc', label: 'Nome (A-Z)' },
  { value: 'name-desc', label: 'Nome (Z-A)' },
  { value: 'price-asc', label: 'Preço: menor → maior' },
  { value: 'price-desc', label: 'Preço: maior → menor' },
];

interface FilterMenuProps {
  rows: DashboardRow[];
  sortOption: SortOption;
  hiddenIds: string[];
  onSortChange: (option: SortOption) => void;
  onToggleHidden: (id: string) => void;
  onShowAll: () => void;
  onReset: () => void;
}

export function FilterMenu({
  rows,
  sortOption,
  hiddenIds,
  onSortChange,
  onToggleHidden,
  onShowAll,
  onReset,
}: FilterMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const wrapperRef = useRef<HTMLDivElement>(null);

  const isActive = sortOption !== 'default' || hiddenIds.length > 0;

  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsOpen(false);
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKey);
    };
  }, [isOpen]);

  const filteredRows = query.trim()
    ? rows.filter((r) => r.name.toLowerCase().includes(query.trim().toLowerCase()))
    : rows;

  return (
    <div className={styles.wrapper} ref={wrapperRef}>
      <button
        type="button"
        className={styles.trigger}
        aria-label="Filtrar e ordenar produtos"
        onClick={() => setIsOpen((prev) => !prev)}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="4" y1="6" x2="20" y2="6" />
          <line x1="8" y1="12" x2="16" y2="12" />
          <line x1="11" y1="18" x2="13" y2="18" />
        </svg>
        {isActive && <span className={styles.activeDot} />}
      </button>

      {isOpen && (
        <div className={styles.panel}>
          <div className={styles.section}>
            <span className={styles.sectionTitle}>Ordenar por</span>
            {SORT_OPTIONS.map((option) => (
              <label key={option.value} className={styles.radioRow}>
                <input
                  type="radio"
                  name="dashboard-sort"
                  value={option.value}
                  checked={sortOption === option.value}
                  onChange={() => onSortChange(option.value)}
                />
                {option.label}
              </label>
            ))}
          </div>

          <div className={styles.divider} />

          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionTitle}>Mostrar</span>
              <button type="button" className={styles.linkButton} onClick={onShowAll}>
                Marcar todos
              </button>
            </div>
            <input
              type="text"
              className={styles.searchInput}
              placeholder="Buscar..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <div className={styles.checklist}>
              {filteredRows.length === 0 ? (
                <span className={styles.emptyChecklist}>Nenhum item encontrado.</span>
              ) : (
                filteredRows.map((row) => (
                  <label key={row.id} className={styles.checkRow}>
                    <input
                      type="checkbox"
                      checked={!hiddenIds.includes(row.id)}
                      onChange={() => onToggleHidden(row.id)}
                    />
                    <span className={styles.checkRowLabel}>{row.name}</span>
                  </label>
                ))
              )}
            </div>
          </div>

          <div className={styles.footer}>
            <button type="button" className={styles.linkButton} onClick={onReset}>
              Limpar filtro
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
