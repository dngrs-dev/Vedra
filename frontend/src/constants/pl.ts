/** Все тексты интерфейса в одном месте (польский). Легко добавить EN позже. */
export const pl = {
  appTitle: 'Vedra',
  appSubtitle: 'Twój asystent gospodarowania wodą',

  search: {
    placeholder: 'Wyszukaj działkę (ID)',
    hint: 'Kliknij na mapie lub wpisz ID działki',
    badFormat: 'Nieprawidłowy format ID. Przykład: 141201_1.0001.6509',
    notFound: 'Nie znaleziono działki o podanym ID',
    unavailable: 'Nie udało się pobrać granic działki.',
    demoFallback: 'Rejestr działek jest chwilowo niedostępny. Pokazano przykładowy obrys (tryb demo).',
    outsidePoland: 'Wybierz lokalizację na terenie Polski'
  },

  map: {
    satellite: 'Satellite',
    terrain: 'Terrain',
    boundaries: 'Granice działek',
    boundariesHint: 'Pokaż granice wszystkich działek i numer po najechaniu',
    boundariesOff: 'Pokaż granice i numery działek',
    boundariesZoomIn: 'Przybliż mapę, aby je zobaczyć',
    boundariesObreby: 'Obręby · przybliż, aby zobaczyć działki',
    boundariesParcels: 'Najedź na działkę, aby zobaczyć numer',
    locate: 'Moja lokalizacja',
    fullscreen: 'Pełny ekran',
    zoomIn: 'Przybliż',
    zoomOut: 'Oddal',
    backToPoland: '← Cała Polska',
    hintRegion: 'Kliknij województwo, aby je przybliżyć',
    hintParcel: 'Kliknij działkę lub przytrzymaj Ctrl i przeciągnij ramkę',
    hintZoom: 'Przybliż mapę, aby wybrać działkę (lub Ctrl + ramka)',
    hintObreby: 'Kliknij działkę · granice działek pojawią się po przybliżeniu',
    showWholeParcel: 'Pokaż całą działkę',
    locateFailed: 'Nie udało się pobrać lokalizacji',
    locateUnavailable: 'Geolokalizacja niedostępna w tej przeglądarce',
    boundariesFailed: 'Granice działek są chwilowo niedostępne — wybór kliknięciem nadal działa',
    hintSelected: 'Zaznaczono. Potwierdź działkę w panelu po prawej',
    regionsFailed: 'granice województw niedostępne'
  },

  selectMode: {
    label: 'Tryb zaznaczania ramką (Ctrl + LPM)',
    simple: 'Zwykły wybór',
    smart: 'Inteligentny wybór',
    simpleTip: 'Ramka = dokładnie zaznaczony prostokąt',
    smartTip: 'Ramka = wszystkie działki, które w większości leżą w środku'
  },

  confirm: {
    button: 'Potwierdź działkę',
    change: 'Zmień działkę',
    selected: 'Wybrana działka',
    custom: 'Własny obszar',
    group: 'Wybrane działki',
    showList: 'Pokaż listę działek',
    tip: 'Obliczenia ruszą dopiero po potwierdzeniu. Możesz jeszcze zmienić uprawę i datę.',
    ctrlTip: 'Przytrzymaj Ctrl (⌘ na Macu) i przeciągnij ramkę. Tryb ramki wybierzesz na górnym pasku: „Zwykły wybór” lub „Inteligentny wybór”.'
  },

  form: {
    crop: 'Wybierz Uprawę',
    cropPlaceholder: 'Wybierz uprawę…',
    date: 'Data analizy',
    dateHint: 'Dziś lub data z ostatnich 10 lat. KBW dotyczy zakończonych okresów monitoringu.'
  },

  moisture: {
    title: 'Ocena Wilgotności i Ryzyka Suszy (10 lat)',
    current: 'Bieżący Stan:',
    avgRisk: 'Średnie Ryzyko Suszy (10 lat):',
    soil: 'Aktualna Wilgotność Gleby:',
    noData: 'Brak danych',
    legendMoisture: 'Wilgotność gleby',
    legendRisk: 'Ryzyko suszy',
    critical: 'Największe ryzyko niedoboru wody:'
  },

  reco: {
    title: 'Zalecenia Retencyjne i Nawodnieniowe',
    retention: 'Zalecenia Retencyjne',
    agro: 'Zalecenia Agrotechniczne',
    irrigation: 'Zalecenia Nawodnieniowe',
    date: 'Optymalny Termin Nawadniania (Prognoza):',
    none: 'Brak',
    why: 'Dlaczego?'
  },

  basis: {
    title: 'Podstawa analizy i źródła danych',
    factors: 'Czynniki uwzględnione w analizie',
    sources: 'Źródła danych'
  },

  status: {
    optimal: 'Optymalny',
    attention: 'Wymaga uwagi',
    critical: 'Krytyczny'
  },
  risk: { low: 'Niskie', moderate: 'Umiarkowane', high: 'Wysokie' },
  confidence: {
    label: 'Wiarygodność wyniku',
    high: 'Wysoka',
    medium: 'Średnia',
    low: 'Niska'
  },
  priority: { high: 'Wysoki priorytet', medium: 'Średni priorytet', low: 'Niski priorytet' },
  sourceStatus: { live: 'na żywo', cached: 'z pamięci podręcznej', unavailable: 'niedostępne' },

  empty: 'Wskaż działkę na mapie lub wpisz jej identyfikator, aby zobaczyć ocenę sytuacji wodnej.',
  error: {
    title: 'Nie udało się wykonać analizy',
    retry: 'Spróbuj ponownie',
    connection: 'Brak połączenia z serwerem',
    invalidParcel: 'Identyfikator wybranej działki jest nieprawidłowy.',
    invalidResponse: 'Serwer zwrócił nieprawidłową odpowiedź.',
    unknown: 'Wystąpił nieznany błąd analizy.'
  },
  demoBanner: 'Dane demonstracyjne. Wyniki są przykładowe i nie opisują wybranego obszaru.',

  backend: {
    site: 'Miejsce',
    sites: 'Miejsca do sprawdzenia',
    siteMap: 'Mapa miejsc do sprawdzenia',
    loadingSiteMap: 'Wczytywanie mapy miejsc…',
    loadingReport: 'Wczytywanie raportu…',
    siteMapLegend: 'Zielony obrys oznacza działkę. Wybierz numer na mapie lub pod nią.',
    siteEvidence: 'Wspólne przesłanki dla działania są w uzasadnieniu.',
    // The landscape rules append this exact caution to affected records (backend texts_pl.py).
    outsideSite: 'Miejsce leży poza działką. Uzgodnij wizję z właścicielem terenu.',
    fieldPlan: 'Plan wizji w terenie',
    fieldNext: 'Od czego zacząć',
    fieldOpenSite: 'Pokaż miejsce na mapie',
    fieldProgress: 'Zapisane obserwacje',
    fieldComplete: 'Zapisano obserwacje dla wszystkich miejsc z tej analizy.',
    fieldLocal: 'Obserwacje są zapisywane w tej przeglądarce dla działki, uprawy i daty analizy.',
    fieldStorageFailed: 'Przeglądarka nie mogła zapisać obserwacji. Pozostanie widoczna do zamknięcia raportu.',
    fieldOutcome: 'Wynik wizji w terenie',
    fieldOutcomes: {
      '': 'Jeszcze niesprawdzone',
      confirmed: 'Potwierdzono warunki na miejscu',
      different: 'Warunki różnią się od oceny'
    },
    preparing: 'Uruchamiam analizę…',
    kbw: 'Klimatyczny bilans wodny (KBW)',
    kbwDefinition: 'Bilans to różnica między opadem a szacowanym parowaniem gleby i roślin przy dostatecznej ilości wody.',
    lastKbwAssessment: 'Ostatnia dostępna ocena',
    balance: 'Wynik',
    verdict: {
      drought: 'Susza rolnicza',
      no_drought: 'Brak suszy rolniczej'
    },
    period: 'Okres oceny',
    soilCategory: 'Kategoria gleby',
    threshold: 'Próg KBW',
    distanceToThreshold: 'Odległość od progu KBW',
    signals: 'Wskaźniki uzupełniające',
    availability: { ok: 'Dostępne', partial: 'Dane częściowe', missing: 'Brak danych' },
    history: 'Podatność historyczna',
    assessedYears: 'Lata objęte oceną',
    droughtYears: 'Lata z suszą',
    noDroughtYears: 'Nie stwierdzono suszy w ocenionych latach',
    causes: 'Możliwe przyczyny niedoboru wody',
    categories: {
      landscape_retention: 'Retencja krajobrazowa',
      soil_retention: 'Retencja glebowa',
      agrotechnics: 'Agrotechnika',
      irrigation: 'Nawadnianie'
    },
    irrigationDate: 'Proponowany termin',
    irrigationDose: 'Dawka netto',
    references: 'Podstawy metodyczne',
    liveSource: 'Pobrano podczas analizy',
    savedSource: 'Źródło zapisane wcześniej',
    noSources: 'Brak dostępnych źródeł.'
  },

  footer: {
    lastUpdate: 'Ostatnia Aktualizacja Danych:',
    report: 'Generuj Raport PDF',
    region: 'Region'
  },

  report: {
    title: 'Raport — ocena sytuacji wodnej działki',
    parcel: 'Dane działki',
    assessment: 'Ocena wilgotności i ryzyka suszy',
    recommendations: 'Zalecenia',
    sources: 'Źródła danych',
    limitations: 'Ograniczenia raportu',
    print: 'Drukuj / Zapisz jako PDF',
    download: 'Pobierz PDF',
    downloadAll: 'Pobierz PDF dla wszystkich upraw',
    downloadReady: 'Pobierz wspólny PDF gotowych raportów',
    downloadAllPending: 'Trwa przygotowanie raportów…',
    downloading: 'Przygotowanie pliku PDF…',
    back: 'Wróć do mapy',
    disclaimer:
      'Raport ma charakter pomocniczy i nie zastępuje oceny agronomicznej. Wynik obarczony jest niepewnością wynikającą z jakości i aktualności danych źródłowych.'
  },

  steps: [
    'Dane satelitarne (Sentinel-2)',
    'Dane meteorologiczne (IMGW / Open-Meteo)',
    'Gleba (IUNG-PIB, SoilGrids)',
    'Hydrologia i ukształtowanie terenu',
    'Obliczanie rekomendacji'
  ]
} as const;

export const MONTHS_PL = [
  'styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec',
  'lipiec', 'sierpień', 'wrzesień', 'październik', 'listopad', 'grudzień'
] as const;
