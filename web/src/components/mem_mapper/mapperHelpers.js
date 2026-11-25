// Pure helpers and default fallback structures for MemMapperTab

export const DEFAULT_SUMMARY = {
  total_words: 512,
  mapped: 0,
  theoretical: 0,
  unknown: 0,
  blank: 0,
  changed: 0,
  coverage_pct: 0
};

export const VALID_AI_CATEGORIES = [
  'counters',
  'maintenance',
  'calibration',
  'settings',
  'faults',
  'hardware',
  'recipe',
  'spdl',
  'custom'
];

export function buildFallbackRegister(selectedAddr) {
  const hexAddr = selectedAddr.toString(16).toUpperCase().padStart(4, '0');
  return {
    addr: selectedAddr,
    hex_addr: hexAddr,
    val: 0,
    val_hex: '0x0000',
    val_dec: 0,
    status: 'blank',
    name: `Reg_0x${hexAddr}`,
    desc: 'Unmapped register',
    category: 'settings',
    unit: '',
    baseline_val: 0,
    baseline_hex: '0x0000',
    delta: 0,
    bits_flipped: [],
    high_byte: 0,
    low_byte: 0,
    signed_val: 0,
    ascii_repr: '..'
  };
}

export function buildFallbackSensorField(selectedFieldKey) {
  return {
    key: selectedFieldKey,
    frame: 'HZ',
    index: 4,
    raw_hex: '03CA',
    raw_dec: 970,
    raw_bin: '0000 0011 1100 1010',
    name: 'Coffee Thermoblock NTC',
    category: 'Thermal',
    unit: '°C',
    scale: 0.1,
    scaled_val: 97.0,
    formatted: '97.0 °C',
    desc: 'Coffee Thermoblock temperature (0.1 °C resolution)',
    notes: 'Thermoblock nominal operating band (90-95°C)'
  };
}

export function filterRegisters(registers, filterType, searchQuery) {
  return registers.filter((r) => {
    if (filterType === 'mapped' && r.status !== 'mapped') return false;
    if (filterType === 'theoretical' && r.status !== 'theoretical') return false;
    if (filterType === 'unknown' && r.status !== 'unknown') return false;
    if (filterType === 'blank' && r.status !== 'blank') return false;
    if (filterType === 'changed' && !r.is_changed) return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchHex = r.hex_addr?.toLowerCase().includes(q);
      const matchName = r.name?.toLowerCase().includes(q);
      const matchDesc = r.desc?.toLowerCase().includes(q);
      const matchCat = r.category?.toLowerCase().includes(q);
      if (!matchHex && !matchName && !matchDesc && !matchCat) return false;
    }
    return true;
  });
}
