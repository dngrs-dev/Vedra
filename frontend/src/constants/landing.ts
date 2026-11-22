/**
 * Treść strony głównej (/). Pisana dla rolnika: prosto, bez żargonu, bez obietnic, których aplikacja nie spełnia.
 * Adresy źródeł - te same co w konfiguracji backendu (backend/config/geo_sources.yaml, crops.yaml,
 * app/reports/builder.py), więc zgadzają się z odnośnikami w raportach.
 */

export interface LandingStep {
  title: string;
  text: string;
}

export interface LandingFeature {
  icon: 'drop' | 'history' | 'pin' | 'leaf' | 'calendar' | 'sliders' | 'spark' | 'file' | 'map';
  title: string;
  text: string;
}

export interface LandingSource {
  name: string;
  /** Co bierzemy z tego źródła - jedno zdanie */
  what: string;
  url: string;
}

export interface LandingSourceGroup {
  title: string;
  sources: LandingSource[];
}

export interface LandingQuestion {
  q: string;
  a: string;
}

export const HERO_LEAD =
  'Wskaż swoją działkę, a sprawdzimy, czy grozi jej susza, gdzie na polu i obok niego da się zatrzymać wodę ' +
  'i czy warto nawadniać. Wynik dostajesz od razu na ekranie i w raporcie PDF.';

export const HERO_STATS: { value: string; label: string }[] = [
  { value: '10 lat', label: 'historii suszy dla działki' },
  { value: 'Każda działka', label: 'ewidencyjna w Polsce' },
  { value: 'Bez rejestracji', label: 'nie trzeba zakładać konta' },
  { value: 'PDF', label: 'także dla kilku upraw' }
];

export const STEPS: LandingStep[] = [
  {
    title: 'Wskaż działkę',
    text: 'Kliknij ją na mapie, wpisz jej numer (identyfikator z ewidencji) albo z wciśniętym Ctrl zaznacz ramką kilka działek naraz.'
  },
  {
    title: 'Wybierz uprawę i datę',
    text: 'Zaznacz, co rośnie na polu - możesz wybrać kilka upraw - i dzień, na który ma być ocena: dziś albo z ostatnich 10 lat.'
  },
  {
    title: 'Potwierdź i odbierz wynik',
    text: 'Po kilku sekundach widzisz ocenę suszy, zalecenia i miejsca na zatrzymanie wody. Całość pobierzesz jako raport PDF.'
  }
];

export const FEATURES: LandingFeature[] = [
  {
    icon: 'drop',
    title: 'Ocena suszy dla Twojej uprawy',
    text: 'Liczymy klimatyczny bilans wodny (KBW): ile wody dał deszcz, a ile zabrało parowanie - i porównujemy z progiem suszy dla wybranej uprawy i gleby.'
  },
  {
    icon: 'history',
    title: '10 lat historii',
    text: 'Widzisz, w ilu latach na tej działce była susza i w których miesiącach ryzyko jest największe.'
  },
  {
    icon: 'pin',
    title: 'Gdzie zatrzymać wodę',
    text: 'Pokazujemy na mapie zagłębienia i miejsca spływu, z numerami i współrzędnymi. „Plan wizji w terenie” podpowiada, od którego miejsca zacząć, a w raporcie odhaczysz sprawdzone.'
  },
  {
    icon: 'leaf',
    title: 'Gleba i jej retencja',
    text: 'Kategoria gleby, ile wody może zatrzymać i co pomoże: próchnica, międzyplony, resztki pożniwne, ściółka.'
  },
  {
    icon: 'calendar',
    title: 'Czy nawadniać',
    text: 'Ocena, czy nawadnianie ma sens przy obecnym zapasie wody w glebie, i jaka dawka wystarczy.'
  },
  {
    icon: 'sliders',
    title: 'Symulacja „Co jeśli?”',
    text: 'Przesuń suwaki - retencja, więcej próchnicy, międzyplony, nawadnianie - i zobacz, o ile dni mniej uprawa cierpiałaby z braku wody.'
  },
  {
    icon: 'spark',
    title: 'Analiza AI prostym językiem',
    text: 'Na życzenie model językowy opisze wyniki w kilku zdaniach. Tylko po Twojej zgodzie - a wszystkie obliczenia i tak wykonuje aplikacja.'
  },
  {
    icon: 'file',
    title: 'Raport PDF do wydruku',
    text: 'Wszystkie wyniki, mapy miejsc i źródła w jednym pliku. Kilka upraw na tej samej działce - w jednym raporcie, bez powtórzeń.'
  },
  {
    icon: 'map',
    title: 'Wygodna mapa',
    text: 'Granice działek po najechaniu, wyszukiwanie po numerze, Twoja lokalizacja na mapie i aktualna pogoda na wybranym polu.'
  }
];

export const SOURCE_GROUPS: LandingSourceGroup[] = [
  {
    title: 'Działki i granice',
    sources: [
      { name: 'GUGiK - ULDK', what: 'Wyszukiwanie działki po numerze lub punkcie na mapie.', url: 'https://uldk.gugik.gov.pl/' },
      { name: 'GUGiK - EGiB', what: 'Granice i numery działek ewidencyjnych.', url: 'https://www.geoportal.gov.pl/pl/dane/ewidencja-gruntow-i-budynkow-egib/' },
      { name: 'GUGiK - PRG', what: 'Granice województw, gmin i obrębów.', url: 'https://www.geoportal.gov.pl/pl/dane/panstwowy-rejestr-granic-prg/' }
    ]
  },
  {
    title: 'Pogoda',
    sources: [
      { name: 'Open-Meteo', what: 'Opady, temperatura i parowanie z ostatnich lat oraz pogoda na dziś.', url: 'https://open-meteo.com/' },
      { name: 'IMGW-PIB', what: 'Pomiary z najbliższej stacji meteorologicznej.', url: 'https://danepubliczne.imgw.pl/' }
    ]
  },
  {
    title: 'Susza',
    sources: [
      { name: 'Rozporządzenie o KBW (Dz.U. 2019 poz. 739)', what: 'Progi suszy dla upraw i kategorii gleb.', url: 'https://eli.gov.pl/api/acts/DU/2019/739/text.pdf' },
      { name: 'IUNG-PIB', what: 'Metoda liczenia klimatycznego bilansu wodnego.', url: 'https://iung.pl/images/wyd/Susza%20rolnicza%20w%20Polsce.pdf' },
      { name: 'European Drought Observatory (Copernicus)', what: 'Europejskie wskaźniki suszy i wilgotności gleby.', url: 'https://drought.emergency.copernicus.eu/' }
    ]
  },
  {
    title: 'Gleba',
    sources: [
      { name: 'Mapa glebowo-rolnicza (GUGiK)', what: 'Rodzaj i kategoria gleby na działce.', url: 'https://www.geoportal.gov.pl/' },
      { name: 'SoilGrids (ISRIC)', what: 'Skład gleby i zdolność zatrzymywania wody.', url: 'https://isric.org/explore/soilgrids/' }
    ]
  },
  {
    title: 'Teren i woda',
    sources: [
      { name: 'NMT (GUGiK) i Copernicus DEM', what: 'Ukształtowanie terenu: zagłębienia i kierunki spływu.', url: 'https://www.geoportal.gov.pl/' },
      { name: 'MPHP10k (Wody Polskie)', what: 'Rzeki, rowy i zlewnie w okolicy.', url: 'https://www.wody.gov.pl/' },
      { name: 'BDOT10k (GUGiK) i OpenStreetMap', what: 'Cieki, drogi i zabudowa przy działce.', url: 'https://www.openstreetmap.org/copyright' }
    ]
  },
  {
    title: 'Zdjęcia satelitarne',
    sources: [
      { name: 'Sentinel-2 (Copernicus)', what: 'Kondycja roślin na działce w kolejnych latach.', url: 'https://planetarycomputer.microsoft.com/' },
      { name: 'ESA WorldCover', what: 'Pokrycie terenu: pola, łąki, lasy, woda.', url: 'https://esa-worldcover.org/' }
    ]
  }
];

export const QUESTIONS: LandingQuestion[] = [
  {
    q: 'Czym jest klimatyczny bilans wodny (KBW)?',
    a: 'To różnica między wodą, która spadła z deszczem, a wodą, która mogła odparować z gleby i roślin. Gdy bilans spada poniżej progu dla danej uprawy i gleby, mówimy o suszy rolniczej. Progi pochodzą z rozporządzenia, a metoda liczenia - z IUNG-PIB.'
  },
  {
    q: 'Czy muszę zakładać konto?',
    a: 'Nie. Wystarczy otworzyć mapę i wskazać działkę. Nie pytamy o imię, nazwisko ani adres e-mail.'
  },
  {
    q: 'Skąd wiecie, która działka jest moja?',
    a: 'Granice i numery działek pochodzą z ewidencji gruntów (GUGiK). Możesz kliknąć pole na mapie albo wpisać numer działki, np. z wypisu z rejestru gruntów.'
  },
  {
    q: 'Jak dokładny jest wynik?',
    a: 'To oszacowanie dla Twojej działki na podstawie publicznych danych pogodowych, glebowych i satelitarnych. Oficjalne wyniki monitoringu suszy publikuje IUNG-PIB. Gdy brakuje danych, raport mówi to wprost.'
  },
  {
    q: 'Co dzieje się z moimi danymi? Co widzi AI?',
    a: 'Analiza AI działa tylko po Twojej zgodzie. Wtedy do dostawcy modelu trafiają: numer i powierzchnia działki, jej gmina, powiat i województwo, uprawa, data oraz wyniki oceny suszy i symulacji „Co jeśli?”. Nie przekazujemy imienia, nazwiska, adresu e-mail ani innych danych kontaktowych.'
  },
  {
    q: 'Czy mogę sprawdzić kilka upraw naraz?',
    a: 'Tak. Zaznacz kilka upraw przed potwierdzeniem działki. Dostaniesz wynik dla każdej z nich i jeden wspólny raport PDF.'
  },
  {
    q: 'Czy to działa na telefonie?',
    a: 'Tak. Strona działa w przeglądarce na telefonie i tablecie, bez instalowania aplikacji.'
  },
  {
    q: 'Czy to zastępuje doradcę rolnego?',
    a: 'Nie. Wyniki mają charakter pomocniczy - pomagają przygotować się do rozmowy z doradcą i do decyzji na polu, ale nie zastępują oceny agronomicznej.'
  }
];
