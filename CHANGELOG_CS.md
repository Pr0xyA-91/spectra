# SPECTRA Diagnostics Suite — Seznam změn (od Build 20261102.1738)

Přehled všech významných novinek, oprav a architektonických milníků aplikace **SPECTRA** od **`Build 20261102.1738`** po **`Build 20261116.1639`**.
V souladu s pravidly projektu jsou verze označovány výhradně **číslem sestavení** (`Build YYYYMMDD.HHMM`).

---

## [Build 20261116.1639] — 2026-11-16

### 🌐 Hlavní novinky: Česká lokalizace rozhraní, interaktivní průvodce a jednoduchý český návod

1. **Čeština jako sekundární jazyk a přepínač v Nastavení (`web/src/i18n/translations.js`, `ConfigModal.jsx`, `spectra_ai.py`, `gui_widgets.py`)**:
   - Přeloženo kompletní webové a desktopové rozhraní (horní lišta, 9 živých KPI kartiček, záložky `01`–`07` a `09`, dialog exportu, monitor ladění, stavová lišta AI i okno Nastavení; vývojářská záložka `08 // MEM MAPPER` zůstala v angličtině).
   - Do horní části okna `CONFIG` / `NASTAVENÍ` přidán okamžitý přepínač **`Language / Jazyk`** (`English (EN)` / `Čeština (CS)`), ukládaný v `localStorage['spectra_lang']` (výchozí jazyk zůstává angličtina).
   - Rozšířeno generování servisního protokolu (`gui_widgets.generate_service_report_html(..., lang="cs")`) a výzvy pro lokální AI (`analyze_fault_triage`, `generate_customer_service_summary` v `spectra_ai.py`), aby při zvolené češtině odpovídaly česky.
2. **Interaktivní průvodce při prvním spuštění (`web/src/components/InteractiveGuideModal.jsx`)**:
   - Vytvořen 7krokový dvojjazyčný interaktivní průvodce, který se automaticky zobrazí při prvním spuštění (`localStorage['spectra_onboarding_seen']`), obsahuje přímý výběr jazyka na úvodní kartě a živá akční tlačítka (přepnutí do režimu `DEMO`, spuštění `⚡ NAČÍST STROJ`, přepínání záložek, otevření nastavení AI a skok na opravu offsetů).
   - Do patičky okna `CONFIG` / `NASTAVENÍ` přidána připomínka s tlačítkem **`Spustit interaktivního průvodce`** a přepínačem pro zobrazení při startu.
3. **Jednoduchá česká uživatelská příručka (`docs/USER_GUIDE_CS.md`)**:
   - Sepsán srozumitelný návod pro běžné uživatele a techniky zaměřený na základní ovládání, připojení lokální AI a opravu špatných počitadel nápojů (CSV / screenshot z aplikace J.O.E.).
4. **Windows instalační a aktualizační balíčky**:
   - Překompilovány soubory `bin/spectra.exe` (25 MB), `dist/spectra_setup.exe` (50 MB) a `dist/spectra_update.exe` (29 MB) pro Build `20261116.1639`.

---

## [Build 20261114.0020] — 2026-11-14

### 🚀 Hlavní novinky: Integrovaná Rust HTTP brána (Fáze 3), ikona okna/lišty a ilustrovaný manuál

1. **Integrovaná Rust HTTP/1.1 brána (`crates/spectra-agent/src/http_gateway.rs`, `crates/spectra-shell/src/main.rs`)**:
   - `spectra-shell` spouští vlastní asynchronní HTTP/1.1 server v Rustu, který přímo servíruje statické soubory UI (`web/dist/`) a řídí Python backend na pozadí přes reverzní proxy.
   - Přidán samostatný režim `--pure-rust` / `--no-python` pro rychlé skenování portů (`/api/ports`), prohlížení knihovny kávovarů (`/api/machines`) a bezpečné příkazy (`/api/command`) bez nutnosti spouštět Python.
2. **Oprava ikony okna a hlavního panelu Windows (`crates/spectra-shell/src/main.rs`)**:
   - Přidán čistě Rustový dekodér nekomprimovaného `.ico` formátu (`decode_ico_entry_to_rgba`) a volání `SetCurrentProcessExplicitAppUserModelID("SPECTRA.Diagnostics.Suite")`, díky čemuž Windows 10/11 správně zobrazuje logo SPECTRA v záhlaví okna i na hlavním panelu.
3. **Ilustrovaná dokumentace (`docs/USER_GUIDE.md`, `docs/images/*.svg`, `README.md`)**:
   - Vytvořena anglická příručka `docs/USER_GUIDE.md` se 4 technickými SVG diagramy popisujícími instalaci, galvanické oddělení, lokální AI, opravu EEPROM offsetů, Mem Mapper a připojení GitHubu.

---

## [Build 20261113.2355] — 2026-11-13

### 🚀 Hlavní novinky: Rozšíření Rust jádra (Fáze 2) a přechod na nativní `spectra-shell`

1. **Rozšíření Rust jádra (`crates/spectra-core/`, `crates/spectra-py/`)**:
   - Do Rustu přesunuty funkce `encode_jura_wire_bytes`, `decode_jura_wire_bytes`, `decode_jura_temperature_word`, `decode_jura_date_word`, `correlate_with_joe_ranked`, `machine_matches_connected` a `load_machine_library`.
   - Zkompilovány nativní moduly pro Linux (`spectra_py.so`) i Windows (`bin/spectra_py.pyd`) se záložním řešením v Pythonu.
2. **Nativní desktopový obal `spectra-shell` jako výchozí**:
   - `spectra_app.py` a Windows spouštěč `launcher.c` nově spouštějí přímo nativní okno `spectra-shell` + `WebView2Loader.dll` bez zátěže `.NET` / `pywebview`.

---

## [Build 20261113.2320] a [Build 20261113.2245] — 2026-11-13

### 🚀 Hlavní novinky: První verze `spectra-shell`, zapamatování okna, dialogy v popředí a oprava TLS na Windows

1. **Jedno-okenní shell `spectra-shell` a paměť polohy okna (`crates/spectra-shell/src/main.rs`)**:
   - Odstraněny skryté pomocné okna na Windows (`.NET-BroadcastEventWindow`, `GDI+ Window`).
   - Okno se při prvním spuštění otevírá maximalizované a ukládá velikost i pozici do `window_state.json`.
2. **Oprava dialogů „Uložit jako / Otevřít“ na Windows (`hmi_inspector.py`)**:
   - Systémovým dialogům (`GetSaveFileNameW` / `GetOpenFileNameW`) se správně předává vlastnické okno `hwndOwner` a focus hook (`OFN_ENABLEHOOK`), takže se už neschovávají za hlavní okno aplikace.
3. **Oprava chyby certifikátů HTTPS na Windows (`tls_utils.py`)**:
   - Přidán modul `tls_utils.py` a certifikáty `certifi` (včetně zálohy přes Windows SChannel), který na čistých instalacích Windows opravil chybu `[SSL: CERTIFICATE_VERIFY_FAILED]` při stahování lokální AI a komunikaci s GitHubem.

---

## [Build 20261113.2205], [Build 20261113.1425] a [Build 20261113.1350] — 2026-11-13

### 🚀 Hlavní novinky: Lokální AI (výchozí VYP), kalibrace offsetů z CSV/screenshotů, knihovna 172 kávovarů a Inspektor firmwaru

1. **Lokální AI bez zátěže ve výchozím stavu (`spectra_ai.py`, `AiStatusBar.jsx`, `ConfigModal.jsx`)**:
   - Lokální AI běží na `127.0.0.1:11434` a je ve výchozím stavu striktně **VYP** (`0 MB RAM`).
   - Přidán automatický 3krokový instalátor přenosného enginu i modelů (`qwen2.5:0.5b`, `gemma3:1b`, `gemma2:2b`, vision model `gemma3:4b`) s ukazatelem rychlosti a průběhu.
   - Přidána AI servisní diagnóza závad (`RUN AI BENCH TRIAGE`) a generování srozumitelného souhrnu pro zákazníka (`GENERATE CUSTOMER SUMMARY`).
2. **Oprava špatných počitadel (CSV i screenshoty) a jednotná knihovna strojů (`machine_library.py`, `DiagnosticAdvisorTab.jsx`)**:
   - Uživatel může v záložce Přehled nahrát CSV z aplikace **J.O.E.** nebo snímek obrazovky (čtený modelem `gemma3:4b` nebo OCR) a opravit tak špatné EEPROM offsety lokálně (`eeprom_overrides.json`), případně opravu exportovat jako `.json` záplatu nebo odeslat komunitě.
   - V okně `CONFIG` přidána prohledávatelná knihovna 172+ kávovarů s prioritou `Lokální oprava > Ověřená specifikace > Vestavěný profil`.
3. **Záložka `09 // FIRMWARE INSPECTOR` a oprava neviditelného okna na Windows**:
   - Modul „HMI Tools“ přejmenován na **Firmware Inspector** a vylepšen export HTML reportů.
   - Opraven příznak `SW_SHOWNORMAL` v `launcher.c`, kvůli kterému se okno WebView2 na Windows spouštělo skrytě.

---

## [Build 20261112.1820] — 2026-11-12

### 🚀 Hlavní novinky: Oprava pádu exportu na Windows, odolný J.O.E. korelátor a nahrávání na GitHub

1. **Oprava pádů při exportu v Pythonu 3.12 na Windows (`hmi_inspector.py`, `test_annotations_resolve.py`)**:
   - Doplněny chybějící importy typových anotací (`Set`, `Union`, `Callable`, `Iterable`, `Sequence`), které způsobovaly chybu `NameError` při importu na Windows.
   - Přidán automatický test `test_annotations_resolve.py` ověřující typové anotace napříč všemi moduly a zavedeno zálohové stažení v prohlížeči při nedostupném systémovém dialogu.
2. **Odolnější čtení CSV z aplikace J.O.E. (`spectra_probe.py`)**:
   - Přidána funkce `_coerce_int()` pro čísla s oddělovači tisíců (`"1 234"`, `"1,234"`) a bezpečné přeskočení nečíselných řádků.
3. **Připojení k GitHubu a komunitní odesílání (`github_auth.py`, `SpectraWorkspace.jsx`)**:
   - Implementováno přihlášení přes GitHub OAuth Device Flow a Personal Access Token (PAT) s bezpečným uložením do systémové klíčenky nebo souboru s právy `0600`.
   - Přepracován dialog Export: rozlišení mezi lokálním uložením a dobrovolným odesláním do `Pr0xyA-91/spectra-captures` (včetně automatického vytvoření Gistu pro velké záznamy nad 64 KB).

---

## [Build 20261110.1445] — 2026-11-10

### 🚀 Hlavní novinky: Nativní dialogy „Uložit jako“ a oprava pádu serveru při exportu

1. **Nativní dialogy pro uložení exportu (`hmi_inspector.py`)**:
   - Přidán nativní Win32 dialog `GetSaveFileNameW` na Windows a GTK3 / `zenity` / `kdialog` / `tkinter` kaskáda na Linuxu pro `/api/export`, `/api/export_capture` a `/api/hmi/export_report`.
2. **Odstranění předčasného ukončení aplikace při exportu (`SpectraWorkspace.jsx`, `web_server.py`, `spectra_app.py`)**:
   - Přesměrování přes `window.location.href` spouštělo událost `beforeunload` a omylem vypínalo Python server; exporty byly převedeny na asynchronní `fetch` volání na pozadí.

---

## [Build 20261110.1355] — 2026-11-10

### 🚀 Hlavní novinky: Čistě grafický spouštěč bez černého okna příkazového řádku a branding SPECTRA

1. **Odstranění okna konzole na Windows (`launcher.c`)**:
   - `spectra.exe` přelinkován jako čistá Win32 GUI aplikace (`-Wl,/subsystem:windows`) spouštějící `pythonw.exe` s `CREATE_NO_WINDOW`.
2. **Animovaná úvodní obrazovka (Splash) a ikony (`launcher.c`, `spectra_app.py`, `index.html`)**:
   - Přidáno tmavé úvodní okno s logem SPECTRA a ukazatelem načítání, které samo zmizí po otevření hlavního okna, a nastaveno sjednocené `AppUserModelID` na hlavním panelu Windows.

---

## [Build 20261110.1150] — 2026-11-10

### 🚀 Hlavní novinky: Zabalený PyWebView pro Windows a vlastní výběr AI modelů

1. **Přímé zabalení `pywebview` a `pythonnet` do Windows balíčku (`src_launcher/build.sh`)**:
   - Zajištěna podpora vestavěného okna i při rychlé aktualizaci (`spectra_update.exe`) a rozšířeno hledání prohlížečů (Edge, Chrome, Brave, Vivaldi, Opera).
2. **Vlastní tmavá rozbalovací nabídka AI modelů (`HmiInspectorTab.jsx`)**:
   - Nahrazen nativní OS `<select>` vlastním React prvkem s vyhledáváním, štítky RAM a záložním katalogem modelů.

---

## [Build 20261110.1105] — 2026-11-10

### 🚀 Hlavní novinky: Oprava předání procesu Edge na Windows a živý stav AI

1. **Oprava předčasného ukončení při předání procesu Edge (`spectra_app.py`, `App.jsx`)**:
   - Zaveden periodický heartbeat `/api/app/heartbeat` (každé 2 s) zabraňující vypnutí serveru, když `msedge.exe` předá okno již běžící instanci.
2. **Živý stav AI služby a ukazatel průběhu skenování (`hmi_inspector.py`, `HmiInspectorTab.jsx`)**:
   - Přidáno sledování obsazené paměti RAM/VRAM přes `/api/ps` a průběžný progress bar hluboké sémantické analýzy (`/api/hmi/semantic/progress`).

---

## [Build 20261110.1008] — 2026-11-10

### 🚀 Hlavní novinky: Kaskáda výběru souborů, oprava skenování sériových portů a přepínač Auto-Scan

1. **Kaskáda nativních dialogů pro výběr souboru (`prompt_file_browser`)**:
   - Bezpečný výběr souborů na Linuxu (GTK3 → `zenity` → `kdialog` → `yad` → `tkinter`) i Windows (Win32 `GetOpenFileNameW` → PowerShell → `tkinter`).
2. **Čisté vyhledávání sériových portů (`serial_io.py`)**:
   - Na Linuxu odstraněny pseudoterminály `/dev/pts/*` a prázdné `/dev/ttyS*` (zabráněno posílání dotazů do terminálů); na Windows čteny reálné porty z registru `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM`.
3. **Přepínač `AUTO-SCAN` a spouštěč na plochu (`HmiInspectorTab.jsx`, `SPECTRA.desktop`)**:
   - Automatické skenování složky Stažené soubory u inspektora firmwaru je nově přepínatelné a uložené v `localStorage`.

---

## [Build 20261109.2255] — 2026-11-09

### 🚀 Hlavní novinky: Dynamické číslo sestavení v záhlaví, řízení cache a ikona aplikace na Linuxu

- Číslo sestavení v horní liště UI se dynamicky čte z `/api/version` a `version.py`.
- Zakázáno kešování statických souborů (`Cache-Control: no-store`) a přidána čistá integrace ikony a `StartupWMClass` pro Wayland/Hyprland v `SPECTRA.desktop`.

---

## [Build 20261109.2230] — 2026-11-09

### 🚀 Hlavní novinky: Dynamické vyhledávání firmwaru a zákaz natvrdo zadaných cest

- Odstraněny všechny pevné lokální cesty v kódu; `KalermHmiInspector.discover_local_targets` dynamicky vyhledává soubory firmwaru pomocí hlaviček ELF32 (`\x7fELF`, ARM) a přidány endpointy `/api/hmi/discover` a `/api/hmi/browse`.
- Obecná ID nálezů (`AUDIT-SWAP-*`, `AUDIT-LEAK-*`, `AUDIT-TYPO-*`) a automatický překlad názvů jazyků.

---

## [Build 20261109.2200] — 2026-11-09

### 🚀 Hlavní novinky: Podpora Android APK a MCU `.bin` firmwarů v Inspektoru firmwaru

- `hmi_inspector.py` rozšířen o automatické rozpoznání kontejnerů `ELF32_LVGL`, `ANDROID_APK` (parser `resources.arsc` a kontrola podpisového schématu v2) a `MCU_CTR_BIN` (tabulka vektorů přerušení STM32H7/GD32F4 a párování CRC).
- Vylepšen tmavý motiv pro GTK3/WebKit2 a čitelnost rozbalovacích nabídek.

---

## [Build 20261109.1500] — 2026-11-09

### 🚀 Hlavní novinky: Obecný heuristický auditor lokalizací firmwaru

- Zavedeny 4 obecné heuristiky napříč všemi jazyky: detekce úniku cizích řetězců/ukazatelů a CJK znaků, kontrola pravopisných překlepů a formátovacích značek `printf` (`%d`, `%s`), kontrola sémantických záměn (`vysoká`/`nízká`, proplach napěňovače vs. externí hadička) a kontrola tabulky výběru jazyků.
- Přidán přepínač cílového jazyka auditu v `HmiInspectorTab.jsx` a 18 jednotkových testů v `test_hmi_inspector.py`.

---

## [Build 20261109.1339] — 2026-11-09

### 🚀 Hlavní novinky: První verze Kalerm HMI Firmware & Translation Inspector (`hmi_inspector.py`)

- Dynamické čtení ELF32 sekcí/symbolů (`lv_i18n_language_pack`, 19 jazyků, 650+ frází), automatická detekce lokalizačních i logických chyb, laboratorní binární záplatovač (`apply_patches()`), ověření SHA-256/RSA podpisů a export reportů do Markdown/HTML/PDF.
- Integrace do GTK3 dialogu (`HmiInspectorDialog`) a CLI (`--hmi-inspect`, `--hmi-patch`, `--hmi-export-report`).

---

## [Build 20261104.1418] — 2026-11-04

### 🚀 Hlavní novinky: Úprava teplotního rozsahu připravenosti termobloku

- V komponentě `DigitalTwinSchematic.jsx` rozšířen rozsah stavu `READY` u kávového termobloku `TB1` z `90–100 °C` na `80–115 °C`, aby provozní teploty kolem `100,5 °C` nebyly chybně označovány jako `HEATING`.
- Ověřeno na displejové podsběrnici `EF518D V02.04` (`RT$:00..F0`, `RE$:00..0F`), že příkazy `TP$:` a `T1$:..T3$:` podporují pouze displeje řady Zeta.

---

## [Build 20261104.1350] — 2026-11-04

### 🚀 Hlavní novinky: Detailní průzkum podsběrnice displeje (`EF518D V02.04`) a zobrazení původu čidla zrn

- Sériovým testováním na živém stroji potvrzeno, že `CS$:` (`cs$:1418`), `RE$:` i `RT$:` na `EF518D` jsou vůči stavu zásobníku zrn neměnné.
- DLAŽDICE 7 (`BEAN HOPPER`) a uzel v `DigitalTwinSchematic.jsx` u komerčních dvoudeskových modelů `EF518` nově zobrazují stav **`LOCAL (EF518D)`** (*„Hlídáno lokálně displejem (EF518D)“*) místo pevného „Hopper Charged“.

---

## [Build 20261104.1305] — 2026-11-04

### 🚀 Hlavní novinky: Kompletní 512slovný důkaz EEPROM a bezpečné vyhodnocení připravenosti

- Porovnáním všech 512 slov EEPROM (`RT:0000..01F0`) na živém stroji Jura IMPRESSA XJ5 (`EF518M` / `EF518D`) potvrzeno, že optická závora zrn je připojena lokálně jen k čelní desce displeje a po sériové lince se nepřenáší.
- `machine_ready` v `stats_collector.py` sjednoceno striktně na 5 fyzických vstupů (odkapní miska, nádržka vody, zásobník sedliny, termoblok $\ge 80\,^\circ\text{C}$, klidový stav), vyhodnocení zrn ponecháno na tloušťce kávového puku ($\le 14$ tiků) a zachováno rychlé dotazování (`fast_poll=True`, ~50 ms).

---

## [Build 20261103.1925] — 2026-11-03

### 🚀 Hlavní novinky: Statická analýza displejového firmwaru a dešifrování `.t3s` skriptů

- Disassemblovány příkazy displejové desky `FlashDisplayZeta V4.0.4` (`#RB$`, `TP$`, `TS$`, `ST$`, `T1$`–`T3$`, `TY$`).
- Rozluštěna rotační šifra Top-Tronic v servisních XML definicích `Serv_EF518_V2.t3s` (potvrzeno, že `00B3` bit `0x0040` řídí zámek šachty pro mletou kávu, nikoli senzor zrn).

---

## [Build 20261103.1806] — 2026-11-03

### 🚀 Hlavní novinky: Odstranění falešných blokací čidla zrn a analýza sběrnice `$:`

- Odstraněny blokace připravenosti založené na nestabilních příznacích relace (`CS[39:43]`, `RE:0029`, `HZ[0][3]`), které po restartu stroje vyvolávaly falešné hlášení „Doplnit zrna“.
- Odstraněna chybná karta `optical_bean_sensor` v seznamu senzorů (nahrazena ověřeným autotestem NTC čidla ohřívače `AS:`) a zmapována skoková tabulka příkazů `$:` v firmwaru Renesas R8C.

---

## [Build 20261103.1330] a [Build 20261103.1225] — 2026-11-03

### 🚀 Hlavní novinky: Zpětné inženýrství příkazu `AS:` a reset chyb `FA:01`

- Rozbor servisního programu `P518Ani.exe` (`VA 0x004E6E28`) prokázal, že příkaz `AS:` není optický senzor zrn, ale **autotest NTC čidla kávového termobloku** s kalibračním bočníkem $+6{,}0\,\%$ (`180 < OFF_ADC < 17000`, poměr $\text{ON}/\text{OFF} \approx 1{,}060 \pm 0{,}010$).
- Zdokumentován diagnostický příkaz `FA:01` (vymazání paměti závad `RE:0028` a bezpečný přechod do pohotovosti) a chování `RR:` / `RE:0029`.
- *(Pozn.: Experimentální vázání připravenosti na `RE:0029` ze sestavení `20261103.1330` bylo následně v `20261103.1806` upraveno po ověření chování na živém hardwaru).*

---

## [Build 20261102.1738] — 2026-11-02

### 🚀 Hlavní novinky: Samostatná sada pro Windows, stabilizace komunikace a 3vrstvá architektura v Rustu

1. **Windows offline instalátor, rychlý aktualizátor a spouštěč**:
   - Vytvořen nativní PE32+ instalátor (`spectra_setup_build20261102.1738.exe`) s vestavěným Pythonem 3.12, `pyserial` a React UI, rychlý aktualizátor (`spectra_update_build20261102.1738.exe`) a spouštěč `bin/spectra.exe`.
2. **Stabilita sériového portu a HTTP serveru na Windows**:
   - Opraveny chyby `WinError 10053`, odstraněno zbytečné volání `SetCommTimeouts` při 20Hz dotazování, přidáno filtrování ojedinělých výpadků komunikace a ochrana proti hromadění paralelních požadavků v prohlížeči (`inFlightPollRef`).
3. **3vrstvá hybridní architektura v Rustu (`crates/spectra-*`)**:
   - `spectra-hal` (sériové porty + Android ADB), `spectra-core` (protokolové dekodéry pro Jura, Nivona, Kalerm, Jetinno, EEPROM a J.O.E. korelátor), `spectra-agent` (asynchronní IPC) a `spectra-py` (`spectra_py.so`).
4. **Sjednocení podpory více výrobců a číslování sestavení**:
   - Sjednoceny ovladače pro **Jura** (ASCII + šifrovaný `@` Smart Connect), **Nivona**, **Lamanti-KL (Kalerm)** a **Lamanti-JN (Jetinno)**, oddělena živá připravenost (`HZ:`) od historických chyb v EEPROM (`RE:0028`, `RE:01B4`), přidán nástroj `spectra_probe.py` a zavedeno výhradní značení pomocí čísel sestavení (`Build YYYYMMDD.HHMM`).
