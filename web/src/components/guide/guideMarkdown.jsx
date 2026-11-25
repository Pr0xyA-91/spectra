import React from 'react';
import {
  Info,
  Lightbulb,
  AlertTriangle,
  ShieldAlert,
  BookmarkCheck,
  ZoomIn,
  ExternalLink,
} from 'lucide-react';
import { safeExternalUrl } from '../../utils/urlSafety';

/**
 * Convert a Markdown heading string into a GitHub-style slug for in-guide cross-links.
 */
export function slugifyHeading(text = '') {
  return String(text)
    .toLowerCase()
    .replace(/[`*_~]/g, '')
    .replace(/[^\p{L}\p{N}\s-]/gu, '')
    .trim()
    .replace(/\s+/g, '-');
}

/**
 * Strip leading chapter numbering like "1. " or "11. " for clean badges while preserving display title.
 */
function extractChapterMeta(headingLine, fallbackIndex) {
  const clean = headingLine
    .replace(/^##\s+/, '')
    .replace(/`/g, '')
    .replace(/\*\*/g, '')
    .trim();
  const match = clean.match(/^(\d+)\.\s+(.*)$/);
  if (match) {
    return {
      number: match[1].padStart(2, '0'),
      shortTitle: match[2].trim(),
      fullTitle: clean,
      slug: slugifyHeading(clean),
    };
  }
  return {
    number: String(fallbackIndex).padStart(2, '0'),
    shortTitle: clean,
    fullTitle: clean,
    slug: slugifyHeading(clean),
  };
}

/**
 * Split a Markdown user guide into structured chapters, skipping the static Table of Contents
 * (since the modal provides a live searchable sidebar TOC).
 */
export function parseGuideDocument(markdownText = '') {
  const lines = String(markdownText).replace(/\r\n/g, '\n').split('\n');
  let docTitle = 'SPECTRA User Guide';
  let subtitleLines = [];
  const rawSections = [];

  let currentSection = null;
  let seenFirstH2 = false;

  for (const line of lines) {
    if (!seenFirstH2 && /^#\s+/.test(line)) {
      docTitle = line.replace(/^#\s+/, '').trim();
      continue;
    }
    if (/^##\s+/.test(line)) {
      seenFirstH2 = true;
      if (currentSection) rawSections.push(currentSection);
      currentSection = { headingLine: line, bodyLines: [] };
      continue;
    }
    if (!seenFirstH2) {
      subtitleLines.push(line);
    } else if (currentSection) {
      currentSection.bodyLines.push(line);
    }
  }
  if (currentSection) rawSections.push(currentSection);

  // Filter out static Markdown TOC sections ("Obsah", "Table of Contents", "Contents")
  const filtered = rawSections.filter((sec) => {
    const h = sec.headingLine.replace(/^##\s+/, '').trim().toLowerCase();
    return h !== 'obsah' && h !== 'table of contents' && h !== 'contents';
  });

  // Build chapters + collect every heading slug for cross-chapter anchor jumps
  const anchorToChapterIdx = {};
  const chapters = filtered.map((sec, idx) => {
    const meta = extractChapterMeta(sec.headingLine, idx + 1);
    const body = sec.bodyLines.join('\n').trim();
    anchorToChapterIdx[meta.slug] = idx;

    // Collect h3/h4 slugs inside this chapter
    for (const bLine of sec.bodyLines) {
      const hm = bLine.match(/^#{3,4}\s+(.*)$/);
      if (hm) {
        const subSlug = slugifyHeading(hm[1]);
        if (subSlug) anchorToChapterIdx[subSlug] = idx;
      }
    }

    const plainText = `${meta.fullTitle}\n${body}`
      .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/[`*_#>-]/g, ' ')
      .toLowerCase();

    return {
      idx,
      id: meta.slug,
      number: meta.number,
      shortTitle: meta.shortTitle,
      fullTitle: meta.fullTitle,
      body,
      plainText,
      blocks: parseMarkdownBlocks(body),
    };
  });

  const cleanIntroLines = subtitleLines
    .map((l) => l.replace(/^>\s?/, '').replace(/\*\*/g, '').replace(/`/g, '').trim())
    .filter((l) => l && l !== '---');
  const introText = cleanIntroLines[0] || '';

  return { docTitle, introText, chapters, anchorToChapterIdx };
}

/**
 * Parse a chapter's Markdown body into structured render blocks (zero HTML injection).
 */
function parseMarkdownBlocks(body) {
  const lines = body.split('\n');
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // Blank line
    if (!trimmed) {
      i++;
      continue;
    }

    // Horizontal rule
    if (/^-{3,}$/.test(trimmed) || /^\*{3,}$/.test(trimmed)) {
      blocks.push({ type: 'hr' });
      i++;
      continue;
    }

    // Subheadings (### or ####)
    const hMatch = trimmed.match(/^(#{3,4})\s+(.*)$/);
    if (hMatch) {
      blocks.push({
        type: 'heading',
        level: hMatch[1].length,
        text: hMatch[2].trim(),
        slug: slugifyHeading(hMatch[2].trim()),
      });
      i++;
      continue;
    }

    // Standalone image line: ![alt](src)
    const imgMatch = trimmed.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (imgMatch) {
      blocks.push({
        type: 'image',
        alt: imgMatch[1].trim(),
        src: imgMatch[2].trim(),
      });
      i++;
      continue;
    }

    // GitHub callout or blockquote (> ...)
    if (trimmed.startsWith('>')) {
      const quoteLines = [];
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ''));
        i++;
      }
      const first = quoteLines[0] || '';
      const alertMatch = first.match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]$/i);
      if (alertMatch) {
        blocks.push({
          type: 'alert',
          variant: alertMatch[1].toUpperCase(),
          lines: quoteLines.slice(1),
        });
      } else {
        blocks.push({
          type: 'blockquote',
          lines: quoteLines,
        });
      }
      continue;
    }

    // Markdown table (starts with | and next line is separator | :--- |)
    if (
      trimmed.startsWith('|') &&
      i + 1 < lines.length &&
      /^\|[\s:|-]+\|?$/.test(lines[i + 1].trim())
    ) {
      const splitRow = (rowStr) =>
        rowStr
          .trim()
          .replace(/^\|/, '')
          .replace(/\|$/, '')
          .split('|')
          .map((cell) => cell.trim());

      const headers = splitRow(trimmed);
      i += 2; // skip header + separator
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      blocks.push({ type: 'table', headers, rows });
      continue;
    }

    // Unordered or ordered list (supports nested indented sub-items & inline callout continuation)
    if (/^(\s*)(-|\*|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\.\s+/.test(line);
      const items = [];
      while (i < lines.length) {
        const cur = lines[i];
        const curTrim = cur.trim();
        if (!curTrim) {
          // Stop list on blank line unless immediately followed by another item of same list type
          const next = lines[i + 1] || '';
          const nextMatches = ordered ? /^\d+\.\s+/.test(next.trim()) : /^[-*]\s+/.test(next.trim());
          if (!nextMatches) {
            i++;
            break;
          }
          i++;
          continue;
        }
        const itemMatch = cur.match(/^(\s*)(?:(-|\*)|(\d+)\.)\s+(.*)$/);
        if (itemMatch) {
          const indent = itemMatch[1].length;
          items.push({
            indent,
            num: itemMatch[3] || null,
            text: itemMatch[4].trim(),
            extras: [],
          });
          i++;
          continue;
        }
        // Indented continuation (e.g. indented blockquote or image inside numbered step)
        if (cur.startsWith('  ') && items.length > 0) {
          const lastItem = items[items.length - 1];
          if (curTrim.startsWith('>')) {
            const qLines = [];
            while (i < lines.length && lines[i].trim().startsWith('>')) {
              qLines.push(lines[i].trim().replace(/^>\s?/, ''));
              i++;
            }
            const am = (qLines[0] || '').match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]$/i);
            if (am) {
              lastItem.extras.push({ type: 'alert', variant: am[1].toUpperCase(), lines: qLines.slice(1) });
            } else {
              lastItem.extras.push({ type: 'blockquote', lines: qLines });
            }
            continue;
          }
          lastItem.text += `\n${curTrim}`;
          i++;
          continue;
        }
        break;
      }
      blocks.push({ type: 'list', ordered, items });
      continue;
    }

    // Regular paragraph (merge consecutive plain lines)
    const pLines = [];
    while (i < lines.length) {
      const l = lines[i];
      const lt = l.trim();
      if (
        !lt ||
        /^#{2,4}\s+/.test(lt) ||
        /^!\[[^\]]*\]\([^)]+\)$/.test(lt) ||
        lt.startsWith('>') ||
        lt.startsWith('|') ||
        /^-{3,}$/.test(lt) ||
        /^(\s*)(-|\*|\d+\.)\s+/.test(l)
      ) {
        break;
      }
      pLines.push(lt);
      i++;
    }
    if (pLines.length > 0) {
      blocks.push({ type: 'paragraph', text: pLines.join(' ') });
    } else {
      i++;
    }
  }

  return blocks;
}

/**
 * Render safe inline Markdown tokens: **bold**, *italic*, `code`, [links](url), and <br> breaks.
 */
function renderInline(text, onNavigateAnchor) {
  if (!text) return null;
  // Support explicit <br> or \n breaks inside cells / multi-line list items
  const segments = String(text).split(/<br\s*\/?>|\n/gi);
  if (segments.length > 1) {
    return segments.map((seg, idx) => (
      <React.Fragment key={idx}>
        {idx > 0 && <br />}
        {renderInlineLine(seg, onNavigateAnchor)}
      </React.Fragment>
    ));
  }
  return renderInlineLine(text, onNavigateAnchor);
}

function renderInlineLine(line, onNavigateAnchor) {
  const tokenRegex = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\*[^*]+\*)/g;
  const parts = String(line).split(tokenRegex);
  return parts.map((part, idx) => {
    if (!part) return null;

    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return (
        <strong key={idx} className="font-bold text-zinc-100">
          {renderInlineLine(part.slice(2, -2), onNavigateAnchor)}
        </strong>
      );
    }

    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code
          key={idx}
          className="px-1.5 py-0.5 rounded bg-zinc-900/90 border border-zinc-700/80 text-[#FCEE09] font-mono text-[0.88em]"
        >
          {part.slice(1, -1)}
        </code>
      );
    }

    if (part.startsWith('[') && part.includes('](') && part.endsWith(')')) {
      const m = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (m) {
        const [, label, href] = m;
        if (href.startsWith('#')) {
          return (
            <button
              key={idx}
              type="button"
              onClick={() => onNavigateAnchor(href.slice(1))}
              className="text-sky-400 hover:text-sky-300 underline decoration-sky-500/50 underline-offset-2 cursor-pointer font-medium"
            >
              {label}
            </button>
          );
        }
        const safeHref = safeExternalUrl(href);
        if (safeHref) {
          return (
            <a
              key={idx}
              href={safeHref}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sky-400 hover:text-sky-300 underline decoration-sky-500/50 underline-offset-2 font-medium"
            >
              <span>{label}</span>
              <ExternalLink className="w-3 h-3 inline shrink-0" />
            </a>
          );
        }
        return <span key={idx}>{label}</span>;
      }
    }

    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return (
        <em key={idx} className="italic text-zinc-300">
          {renderInlineLine(part.slice(1, -1), onNavigateAnchor)}
        </em>
      );
    }

    return <React.Fragment key={idx}>{part}</React.Fragment>;
  });
}

const ALERT_STYLES = {
  TIP: {
    border: 'border-emerald-600/60',
    bg: 'bg-emerald-950/30',
    titleColor: 'text-emerald-300',
    icon: Lightbulb,
    labelEn: 'TIP',
    labelCs: 'TIP',
  },
  NOTE: {
    border: 'border-sky-600/60',
    bg: 'bg-sky-950/30',
    titleColor: 'text-sky-300',
    icon: Info,
    labelEn: 'NOTE',
    labelCs: 'POZNÁMKA',
  },
  IMPORTANT: {
    border: 'border-indigo-500/60',
    bg: 'bg-indigo-950/35',
    titleColor: 'text-indigo-300',
    icon: BookmarkCheck,
    labelEn: 'IMPORTANT',
    labelCs: 'DŮLEŽITÉ',
  },
  WARNING: {
    border: 'border-amber-500/70',
    bg: 'bg-amber-950/35',
    titleColor: 'text-amber-300',
    icon: AlertTriangle,
    labelEn: 'WARNING',
    labelCs: 'UPOZORNĚNÍ',
  },
  CAUTION: {
    border: 'border-rose-500/75',
    bg: 'bg-rose-950/40',
    titleColor: 'text-rose-300',
    icon: ShieldAlert,
    labelEn: 'SAFETY CAUTION',
    labelCs: 'BEZPEČNOSTNÍ POZOR',
  },
};

function renderAlertBlock(block, guideLang, onNavigateAnchor, key) {
  const st = ALERT_STYLES[block.variant] || ALERT_STYLES.NOTE;
  const Icon = st.icon;
  return (
    <div
      key={key}
      className={`my-4 p-3.5 rounded-lg border ${st.border} ${st.bg} space-y-1.5 text-[13px] leading-relaxed`}
    >
      <div className={`flex items-center gap-2 font-mono text-[11px] font-extrabold tracking-wider ${st.titleColor}`}>
        <Icon className="w-4 h-4 shrink-0" />
        <span>{guideLang === 'cs' ? st.labelCs : st.labelEn}</span>
      </div>
      <div className="space-y-1 text-zinc-200">
        {block.lines
          .filter((l) => l.trim().length > 0)
          .map((l, idx) => (
            <p key={idx}>{renderInline(l, onNavigateAnchor)}</p>
          ))}
      </div>
    </div>
  );
}

/**
 * Resolve guide image path cleanly to /guide/<relativePath>
 */
function resolveGuideImageSrc(rawSrc) {
  if (!rawSrc || typeof rawSrc !== 'string') return '';
  const trimmed = rawSrc.trim();
  if (!trimmed) return '';
  // Reject protocol-relative URLs (//...) and external schemes (http:, https:, javascript:, data:, etc.)
  if (trimmed.startsWith('//') || /^[a-z][a-z0-9+.-]*:/i.test(trimmed)) {
    return '';
  }
  if (trimmed.startsWith('/guide/')) return trimmed;
  if (trimmed.startsWith('/')) return '';
  return `/guide/${trimmed.replace(/^\.\//, '')}`;
}

export function GuideChapterRenderer({
  chapter,
  guideLang,
  clickToZoomLabel,
  onNavigateAnchor,
  onZoomImage,
}) {
  if (!chapter) return null;

  return (
    <div className="space-y-4 font-sans text-[14px] leading-relaxed text-zinc-200">
      {chapter.blocks.map((block, idx) => {
        if (block.type === 'hr') {
          return <hr key={idx} className="my-5 border-zinc-800" />;
        }

        if (block.type === 'heading') {
          if (block.level === 3) {
            return (
              <h3
                key={idx}
                id={`guide-sec-${block.slug}`}
                className="pt-3 text-base font-extrabold text-[#FCEE09] tracking-wide border-b border-zinc-800/80 pb-1.5"
              >
                {renderInline(block.text, onNavigateAnchor)}
              </h3>
            );
          }
          return (
            <h4
              key={idx}
              id={`guide-sec-${block.slug}`}
              className="pt-2 text-sm font-bold text-sky-300"
            >
              {renderInline(block.text, onNavigateAnchor)}
            </h4>
          );
        }

        if (block.type === 'paragraph') {
          return (
            <p key={idx} className="text-zinc-300 leading-relaxed">
              {renderInline(block.text, onNavigateAnchor)}
            </p>
          );
        }

        if (block.type === 'alert') {
          return renderAlertBlock(block, guideLang, onNavigateAnchor, idx);
        }

        if (block.type === 'blockquote') {
          return (
            <blockquote
              key={idx}
              className="my-3 pl-3.5 py-2 border-l-2 border-[#FCEE09]/70 bg-black/40 rounded-r text-zinc-200 space-y-1"
            >
              {block.lines.map((l, li) => (
                <p key={li}>{renderInline(l, onNavigateAnchor)}</p>
              ))}
            </blockquote>
          );
        }

        if (block.type === 'image') {
          const resolvedSrc = resolveGuideImageSrc(block.src);
          if (!resolvedSrc) return null;
          return (
            <figure
              key={idx}
              className="my-4 rounded-xl border border-zinc-800 bg-black/60 overflow-hidden shadow-lg"
            >
              <button
                type="button"
                onClick={() => onZoomImage({ src: resolvedSrc, alt: block.alt })}
                className="group relative block w-full text-left cursor-zoom-in focus:outline-none"
                title={clickToZoomLabel}
              >
                <img
                  src={resolvedSrc}
                  alt={block.alt}
                  loading="lazy"
                  className="w-full h-auto block transition-transform duration-200 group-hover:scale-[1.005]"
                />
                <span className="absolute bottom-2.5 right-2.5 px-2.5 py-1 rounded-md bg-black/80 border border-zinc-600/80 text-[11px] font-mono font-bold text-zinc-200 flex items-center gap-1.5 opacity-85 group-hover:opacity-100 group-hover:border-[#FCEE09] group-hover:text-[#FCEE09] transition-all">
                  <ZoomIn className="w-3.5 h-3.5" />
                  <span>{clickToZoomLabel}</span>
                </span>
              </button>
              {block.alt && (
                <figcaption className="px-3.5 py-2 text-[12px] text-zinc-400 border-t border-zinc-800/80 bg-zinc-950/70">
                  {block.alt}
                </figcaption>
              )}
            </figure>
          );
        }

        if (block.type === 'table') {
          return (
            <div key={idx} className="my-4 overflow-x-auto rounded-lg border border-zinc-800 bg-black/40">
              <table className="w-full text-left border-collapse text-[13px]">
                <thead>
                  <tr className="bg-zinc-900/90 border-b border-zinc-800 text-zinc-100">
                    {block.headers.map((h, hi) => (
                      <th key={hi} className="px-3 py-2 font-bold text-xs uppercase tracking-wider text-zinc-200">
                        {renderInline(h, onNavigateAnchor)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/70">
                  {block.rows.map((row, ri) => (
                    <tr key={ri} className={ri % 2 === 1 ? 'bg-white/[0.02]' : ''}>
                      {row.map((cell, ci) => (
                        <td key={ci} className="px-3 py-2 align-top text-zinc-300 leading-snug">
                          {renderInline(cell, onNavigateAnchor)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        if (block.type === 'list') {
          return (
            <div key={idx} className="space-y-2 my-2">
              {block.items.map((item, ii) => {
                const isNested = item.indent >= 2;
                return (
                  <div
                    key={ii}
                    className={isNested ? 'pl-7 space-y-1.5' : 'space-y-1.5'}
                  >
                    <div className="flex items-start gap-2.5">
                      {item.num ? (
                        <span className="shrink-0 mt-0.5 w-5 h-5 rounded-full bg-zinc-800 border border-zinc-700 text-[#FCEE09] font-mono text-[11px] font-bold flex items-center justify-center">
                          {item.num}
                        </span>
                      ) : (
                        <span
                          className={`shrink-0 mt-2 w-1.5 h-1.5 rounded-full ${
                            isNested ? 'bg-sky-400' : 'bg-[#FCEE09]'
                          }`}
                        />
                      )}
                      <div className="flex-1 text-zinc-300 leading-relaxed">
                        {renderInline(item.text, onNavigateAnchor)}
                      </div>
                    </div>
                    {item.extras &&
                      item.extras.map((ex, ei) =>
                        ex.type === 'alert' ? (
                          <div key={ei} className="ml-7">
                            {renderAlertBlock(ex, guideLang, onNavigateAnchor, `ex-${ei}`)}
                          </div>
                        ) : (
                          <blockquote
                            key={ei}
                            className="ml-7 pl-3 py-1.5 border-l-2 border-zinc-600 text-zinc-300 text-[13px]"
                          >
                            {ex.lines.map((l, li) => (
                              <p key={li}>{renderInline(l, onNavigateAnchor)}</p>
                            ))}
                          </blockquote>
                        )
                      )}
                  </div>
                );
              })}
            </div>
          );
        }

        return null;
      })}
    </div>
  );
}
