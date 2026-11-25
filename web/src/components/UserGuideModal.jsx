import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  BookOpen,
  X,
  Search,
  ChevronLeft,
  ChevronRight,
  Compass,
  Menu,
  Globe,
} from 'lucide-react';
import { createTranslator, SUPPORTED_LANGUAGES } from '../i18n/translations';
import { parseGuideDocument, GuideChapterRenderer } from './guide/guideMarkdown';

const GUIDE_CACHE = {};

export default function UserGuideModal({
  isOpen,
  onClose,
  theme,
  lang = 'en',
  onOpenInteractiveTour = () => {},
}) {
  const [guideLang, setGuideLang] = useState(lang === 'cs' ? 'cs' : 'en');
  const t = useMemo(() => createTranslator(guideLang), [guideLang]);

  const [parsedDoc, setParsedDoc] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [activeIdx, setActiveIdx] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [zoomedImage, setZoomedImage] = useState(null);
  const [mobileTocOpen, setMobileTocOpen] = useState(false);

  const contentScrollRef = useRef(null);
  const searchInputRef = useRef(null);

  // Sync guide language with active UI language each time modal opens
  useEffect(() => {
    if (isOpen) {
      setGuideLang(lang === 'cs' ? 'cs' : 'en');
      setZoomedImage(null);
      setMobileTocOpen(false);
    }
  }, [isOpen, lang]);

  // Fetch and parse the selected language's baked-in Markdown manual
  useEffect(() => {
    if (!isOpen) return;
    let active = true;
    const code = guideLang === 'cs' ? 'cs' : 'en';

    if (GUIDE_CACHE[code]) {
      setParsedDoc(GUIDE_CACHE[code]);
      setLoadError('');
      setLoading(false);
      return;
    }

    setLoading(true);
    setLoadError('');
    fetch(`/guide/${code}.md`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((text) => {
        if (!active) return;
        const parsed = parseGuideDocument(text);
        GUIDE_CACHE[code] = parsed;
        setParsedDoc(parsed);
        setLoading(false);
      })
      .catch((err) => {
        if (!active) return;
        setLoadError(err?.message || 'Load failed');
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [isOpen, guideLang]);

  const chapters = useMemo(() => parsedDoc?.chapters || [], [parsedDoc]);

  const filteredChapters = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return chapters;
    return chapters.filter((ch) => ch.plainText.includes(q));
  }, [chapters, searchQuery]);

  // Keep activeIdx in bounds when chapters reload
  useEffect(() => {
    if (chapters.length > 0 && activeIdx >= chapters.length) {
      setActiveIdx(0);
    }
  }, [chapters.length, activeIdx]);

  const activeChapter = chapters[activeIdx] || null;

  const selectChapter = useCallback((idx, scrollToSubSlug = null) => {
    setActiveIdx(idx);
    setMobileTocOpen(false);
    requestAnimationFrame(() => {
      if (scrollToSubSlug) {
        const target = document.getElementById(`guide-sec-${scrollToSubSlug}`);
        if (target) {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          return;
        }
      }
      if (contentScrollRef.current) {
        contentScrollRef.current.scrollTo({ top: 0, behavior: 'smooth' });
      }
    });
  }, []);

  const handleNavigateAnchor = useCallback(
    (rawAnchor) => {
      if (!parsedDoc) return;
      const decoded = decodeURIComponent(rawAnchor || '').toLowerCase();
      const targetIdx = parsedDoc.anchorToChapterIdx?.[decoded];
      if (typeof targetIdx === 'number') {
        const isChapterRoot = parsedDoc.chapters[targetIdx]?.id === decoded;
        selectChapter(targetIdx, isChapterRoot ? null : decoded);
      }
    },
    [parsedDoc, selectChapter]
  );

  // Keyboard navigation: Esc closes lightbox -> modal; Left/Right arrows flip chapters
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        if (zoomedImage) {
          setZoomedImage(null);
        } else {
          onClose();
        }
        return;
      }
      if (zoomedImage) return;
      if (document.activeElement === searchInputRef.current) return;
      if (e.key === 'ArrowRight' && activeIdx < chapters.length - 1) {
        e.preventDefault();
        selectChapter(activeIdx + 1);
      } else if (e.key === 'ArrowLeft' && activeIdx > 0) {
        e.preventDefault();
        selectChapter(activeIdx - 1);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, zoomedImage, activeIdx, chapters.length, onClose, selectChapter]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-2 sm:p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={`w-full max-w-6xl h-[92vh] ${theme?.panelBg || 'bg-[#0E0E12]'} border border-zinc-700 rounded-xl shadow-[0_0_50px_rgba(0,0,0,0.9)] flex flex-col overflow-hidden`}
      >
        {/* Top Modal Header */}
        <div className="px-4 py-3 bg-[#14141c] border-b border-zinc-800 flex flex-wrap items-center justify-between gap-2.5 shrink-0">
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => setMobileTocOpen((v) => !v)}
              className="md:hidden p-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-300 hover:text-white cursor-pointer"
              title={t('userGuideTocToggle')}
            >
              <Menu className="w-4 h-4" />
            </button>
            <BookOpen className="w-5 h-5 text-[#FCEE09] shrink-0" />
            <div className="leading-tight">
              <h2 className="text-sm font-mono font-black tracking-wider text-[#FCEE09] uppercase">
                {t('userGuideModalTitle')}
              </h2>
              {parsedDoc?.introText && (
                <p className="text-[11px] text-zinc-400 hidden sm:block truncate max-w-lg">
                  {parsedDoc.introText}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* In-Guide Language Switch (EN / CS) */}
            <div className="flex items-center bg-black/60 border border-zinc-700 rounded-lg p-0.5 font-mono text-[11px]">
              <Globe className="w-3.5 h-3.5 text-zinc-400 mx-1.5" />
              {SUPPORTED_LANGUAGES.map((l) => {
                const active = guideLang === l.id;
                return (
                  <button
                    key={l.id}
                    type="button"
                    onClick={() => setGuideLang(l.id)}
                    className={`px-2 py-1 rounded font-bold transition-colors cursor-pointer ${
                      active
                        ? 'bg-[#00F0FF]/20 text-[#00F0FF] border border-[#00F0FF]/60'
                        : 'text-zinc-400 hover:text-zinc-200 border border-transparent'
                    }`}
                  >
                    {l.short}
                  </button>
                );
              })}
            </div>

            {/* Quick Launch for 7-Step Interactive Tour */}
            <button
              type="button"
              onClick={() => {
                onClose();
                onOpenInteractiveTour();
              }}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-[#FCEE09]/15 hover:bg-[#FCEE09]/25 border border-[#FCEE09]/60 text-[#FCEE09] font-mono text-[11px] font-bold transition-colors cursor-pointer"
              title={t('userGuideInteractiveTourTitle')}
            >
              <Compass className="w-3.5 h-3.5" />
              <span>{t('userGuideInteractiveTourBtn')}</span>
            </button>

            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-400 hover:text-white transition-colors cursor-pointer"
              aria-label="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Main Split Body: Sidebar TOC + Reading Pane */}
        <div className="flex-1 flex min-h-0 relative">
          {/* Left Sidebar: Search + Chapter List */}
          <aside
            className={`${
              mobileTocOpen ? 'flex absolute inset-y-0 left-0 z-20 shadow-2xl' : 'hidden md:flex'
            } w-72 shrink-0 flex-col bg-[#0B0B10] border-r border-zinc-800`}
          >
            {/* Search Input */}
            <div className="p-3 border-b border-zinc-800/80">
              <div className="relative flex items-center">
                <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 pointer-events-none" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t('userGuideSearchPlaceholder')}
                  className="w-full pl-8 pr-7 py-1.5 rounded-lg bg-black/70 border border-zinc-700 focus:border-[#00F0FF] outline-none text-xs text-zinc-100 placeholder-zinc-500"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery('')}
                    className="absolute right-2 text-zinc-500 hover:text-zinc-200 cursor-pointer"
                    title={t('userGuideClearSearch')}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>

            {/* Chapter List */}
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              <div className="px-2 pt-1 pb-1.5 text-[10px] font-mono font-bold tracking-widest text-zinc-500 uppercase">
                {t('userGuideChaptersHeading')} ({filteredChapters.length})
              </div>
              {filteredChapters.length === 0 ? (
                <div className="px-2.5 py-4 text-xs text-zinc-500 text-center">
                  {t('userGuideNoMatches', { query: searchQuery })}
                </div>
              ) : (
                filteredChapters.map((ch) => {
                  const isActive = ch.idx === activeIdx;
                  return (
                    <button
                      key={ch.id}
                      type="button"
                      onClick={() => selectChapter(ch.idx)}
                      className={`w-full text-left px-2.5 py-2 rounded-lg flex items-start gap-2.5 transition-all cursor-pointer border ${
                        isActive
                          ? 'bg-[#FCEE09]/10 border-[#FCEE09]/60 text-white shadow-sm'
                          : 'bg-transparent border-transparent text-zinc-400 hover:bg-zinc-900/70 hover:text-zinc-200'
                      }`}
                    >
                      <span
                        className={`shrink-0 font-mono text-[10px] font-extrabold px-1.5 py-0.5 rounded mt-0.5 ${
                          isActive
                            ? 'bg-[#FCEE09] text-black'
                            : 'bg-zinc-800/90 text-zinc-400'
                        }`}
                      >
                        {ch.number}
                      </span>
                      <span className="text-xs font-medium leading-snug">{ch.shortTitle}</span>
                    </button>
                  );
                })
              )}
            </div>

            {/* Sidebar Footer Hint */}
            <div className="px-3 py-2 border-t border-zinc-800/80 text-[10px] font-mono text-zinc-500">
              {t('userGuideKeyboardHint')}
            </div>
          </aside>

          {/* Right Reading Pane */}
          <div className="flex-1 flex flex-col min-w-0 bg-[#0F0F15]">
            <div ref={contentScrollRef} className="flex-1 overflow-y-auto px-5 sm:px-8 py-6">
              {loading ? (
                <div className="py-20 text-center text-xs font-mono text-zinc-400 animate-pulse">
                  {t('userGuideLoading')}
                </div>
              ) : loadError ? (
                <div className="py-20 text-center space-y-2">
                  <p className="text-sm font-bold text-rose-400">{t('userGuideLoadError')}</p>
                  <p className="text-xs font-mono text-zinc-500">{loadError}</p>
                </div>
              ) : activeChapter ? (
                <article className="max-w-4xl mx-auto pb-8">
                  {/* Chapter Banner Header */}
                  <div className="mb-6 pb-4 border-b border-zinc-800">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="px-2 py-0.5 rounded bg-[#FCEE09]/15 border border-[#FCEE09]/50 text-[#FCEE09] font-mono text-[10px] font-extrabold tracking-wider uppercase">
                        {t('userGuideChapterOf', {
                          current: activeChapter.idx + 1,
                          total: chapters.length,
                        })}
                      </span>
                    </div>
                    <h1 className="text-xl sm:text-2xl font-black text-white tracking-tight">
                      {activeChapter.fullTitle}
                    </h1>
                  </div>

                  {/* Rendered Chapter Content */}
                  <GuideChapterRenderer
                    chapter={activeChapter}
                    guideLang={guideLang}
                    clickToZoomLabel={t('userGuideClickToZoom')}
                    onNavigateAnchor={handleNavigateAnchor}
                    onZoomImage={setZoomedImage}
                  />
                </article>
              ) : null}
            </div>

            {/* Bottom Chapter Flip Pager */}
            {chapters.length > 0 && (
              <div className="px-5 py-3 bg-[#14141c] border-t border-zinc-800 flex items-center justify-between gap-3 shrink-0">
                <button
                  type="button"
                  disabled={activeIdx <= 0}
                  onClick={() => selectChapter(activeIdx - 1)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 disabled:opacity-35 disabled:cursor-not-allowed border border-zinc-700 text-xs font-mono font-bold text-zinc-200 transition-colors cursor-pointer"
                >
                  <ChevronLeft className="w-4 h-4" />
                  <span className="hidden sm:inline">
                    {activeIdx > 0 ? `${chapters[activeIdx - 1].number}. ${chapters[activeIdx - 1].shortTitle}` : t('userGuidePrevChapter')}
                  </span>
                  <span className="sm:hidden">{t('userGuidePrevChapter')}</span>
                </button>

                <span className="text-[11px] font-mono font-bold text-zinc-400 shrink-0">
                  {activeIdx + 1} / {chapters.length}
                </span>

                <button
                  type="button"
                  disabled={activeIdx >= chapters.length - 1}
                  onClick={() => selectChapter(activeIdx + 1)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#FCEE09] hover:bg-yellow-300 disabled:opacity-35 disabled:bg-zinc-800 disabled:text-zinc-500 disabled:cursor-not-allowed text-black text-xs font-mono font-extrabold transition-colors cursor-pointer"
                >
                  <span className="hidden sm:inline">
                    {activeIdx < chapters.length - 1
                      ? `${chapters[activeIdx + 1].number}. ${chapters[activeIdx + 1].shortTitle}`
                      : t('userGuideNextChapter')}
                  </span>
                  <span className="sm:hidden">{t('userGuideNextChapter')}</span>
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Full-Screen Screenshot Lightbox */}
      {zoomedImage && (
        <div
          className="fixed inset-0 z-[60] bg-black/92 backdrop-blur-md flex flex-col items-center justify-center p-4"
          onClick={() => setZoomedImage(null)}
        >
          <button
            type="button"
            onClick={() => setZoomedImage(null)}
            className="absolute top-4 right-4 p-2 rounded-full bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-600 text-white cursor-pointer"
            aria-label="Close zoom"
          >
            <X className="w-5 h-5" />
          </button>
          <img
            src={zoomedImage.src}
            alt={zoomedImage.alt}
            className="max-w-[95vw] max-h-[85vh] object-contain rounded-lg border border-zinc-700 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />
          {zoomedImage.alt && (
            <div className="mt-3 px-4 py-1.5 rounded-full bg-zinc-900/90 border border-zinc-700 text-xs text-zinc-200 max-w-3xl text-center">
              {zoomedImage.alt}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
