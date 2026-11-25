// Shared fallback catalogs, locale lists, and pure helpers for HmiInspectorTab

export const FALLBACK_MODEL_CATALOG = [
  { id: 'qwen2.5:0.5b', name: 'Qwen 2.5 0.5B (Ultra-Light)', min_ram_mb: 800, disk_mb: 398, languages: '29+ CS/EN/DE/ZH', speed_cpu: 'Fast (~1.5s/phrase)', compatibility: 'RECOMMENDED' },
  { id: 'qwen2.5:1.5b', name: 'Qwen 2.5 1.5B (Balanced)', min_ram_mb: 1600, disk_mb: 986, languages: '29+ CS/EN/DE/ZH', speed_cpu: 'Medium (~3.5s/phrase)', compatibility: 'COMPATIBLE' },
  { id: 'llama3.2:1b', name: 'Llama 3.2 1B (Meta)', min_ram_mb: 1200, disk_mb: 1300, languages: 'Multilingual', speed_cpu: 'Fast (~2s/phrase)', compatibility: 'COMPATIBLE' },
  { id: 'gemma2:2b', name: 'Gemma 2 2B (Google)', min_ram_mb: 2600, disk_mb: 1600, languages: 'Multilingual', speed_cpu: 'Moderate (~5s/phrase)', compatibility: 'COMPATIBLE' },
  { id: 'llama3.2:3b', name: 'Llama 3.2 3B (Meta)', min_ram_mb: 3200, disk_mb: 2000, languages: 'Multilingual', speed_cpu: 'Moderate (~4s/phrase)', compatibility: 'COMPATIBLE' },
  { id: 'qwen2.5:3b', name: 'Qwen 2.5 3B (High Accuracy)', min_ram_mb: 3200, disk_mb: 1900, languages: '29+ High Accuracy', speed_cpu: 'Slow without AVX2/GPU', compatibility: 'COMPATIBLE' },
  { id: 'mistral:7b', name: 'Mistral 7B (Mistral AI)', min_ram_mb: 5500, disk_mb: 4100, languages: 'Multilingual', speed_cpu: 'Requires GPU / >=16GB RAM', compatibility: 'HEAVY_FOR_CPU' },
  { id: 'qwen2.5:7b', name: 'Qwen 2.5 7B (Studio Grade)', min_ram_mb: 5800, disk_mb: 4700, languages: '29+ Studio Grade', speed_cpu: 'Requires GPU / >=16GB RAM', compatibility: 'HEAVY_FOR_CPU' },
  { id: 'llama3.1:8b', name: 'Llama 3.1 8B (Meta)', min_ram_mb: 6200, disk_mb: 4900, languages: 'Multilingual', speed_cpu: 'Requires GPU / >=16GB RAM', compatibility: 'HEAVY_FOR_CPU' },
];

export const FALLBACK_LANGUAGES = [
  { locale: 'cs-CZ', phrase_count: 651 },
  { locale: 'de-DE', phrase_count: 651 },
  { locale: 'en-GB', phrase_count: 651 },
  { locale: 'fr-FR', phrase_count: 651 },
  { locale: 'it-IT', phrase_count: 651 },
  { locale: 'es-ES', phrase_count: 651 },
  { locale: 'zh-CN', phrase_count: 651 },
];

export const AUDIT_FALLBACK_LOCALES = [
  'cs-CZ', 'en-GB', 'de-DE', 'da-DK', 'el-GR', 'es-ES', 'fr-FR',
  'hr-HR', 'hu-HU', 'it-IT', 'ja-JP', 'ko-KR', 'nl-NL', 'pl-PL',
  'pt-PT', 'ru-RU', 'sv-SE', 'zh-CN', 'zh-TW',
];

export function buildEffectiveModelCatalog(aiStatus) {
  const catalogMap = new Map();

  // 1. Preload all standard fallback models
  FALLBACK_MODEL_CATALOG.forEach((m) => {
    catalogMap.set(m.id, { ...m, is_installed: false, is_recommended: false });
  });

  // 2. Overlay backend hardware telemetry catalog
  if (aiStatus?.hardware?.model_catalog && Array.isArray(aiStatus.hardware.model_catalog)) {
    aiStatus.hardware.model_catalog.forEach((m) => {
      const existing = catalogMap.get(m.id) || {};
      catalogMap.set(m.id, { ...existing, ...m });
    });
  }

  // 3. Overlay any locally installed models detected in Ollama daemon
  const installed = aiStatus?.ollama?.models || [];
  installed.forEach((ins) => {
    const insId = typeof ins === 'string' ? ins : ins?.name || '';
    if (!insId) return;
    if (catalogMap.has(insId)) {
      catalogMap.get(insId).is_installed = true;
    } else {
      catalogMap.set(insId, {
        id: insId,
        name: `Custom Local: ${insId}`,
        min_ram_mb: 2048,
        disk_mb: 0,
        languages: 'Local Custom Model',
        speed_cpu: 'Custom',
        compatibility: 'COMPATIBLE',
        is_installed: true,
        is_recommended: false,
      });
    }
  });

  // Mark recommended model if matching backend recommendation
  const recId = aiStatus?.hardware?.recommended_model || 'qwen2.5:0.5b';
  if (catalogMap.has(recId)) {
    catalogMap.get(recId).is_recommended = true;
  }

  return Array.from(catalogMap.values());
}
