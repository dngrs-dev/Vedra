# Użycie narzędzi AI

## AI w działającej aplikacji

Wskaźniki, werdykt suszy, przyczyny i rekomendacje oblicza deterministyczny kod według
opisanych metod i reguł. Teksty zaleceń pochodzą z wersjonowanego słownika, a raport zawiera
przesłanki i odsyłacze do źródeł. Model językowy nie tworzy ani nie zmienia tych wyników.
[Metodyka Vedry](METHODOLOGY.md).

Jedyną funkcją AI jest opcjonalny komentarz do symulacji „Co jeśli?”
([`app/ai/insight.py`](../app/ai/insight.py), `POST /api/analyses/{id}/ai-insight`).

| Element | Opis |
| --- | --- |
| Dostawcy | Google Gemini API (domyślnie `gemini-3.5-flash`, zapas `gemini-3.5-flash-lite`) albo Anthropic Claude API (`claude-opus-5-5`, `AI_PROVIDER=anthropic`). |
| Dane wejściowe | JSON z gotowej analizy: identyfikator, powierzchnia i gmina działki, uprawa, data, KBW i próg, historia, przyczyny, rekomendacje, wyniki symulacji, ograniczenia. Bez danych osobowych użytkownika. |
| Wynik | Ustalona struktura: werdykt w jednym zdaniu, prognoza bez działań, najkorzystniejsze działanie, 2–4 uzasadnienia z liczbami, 1–3 zastrzeżenia. |
| Instrukcja dla modelu | Opierać się wyłącznie na liczbach z JSON, nie wymyślać prognoz pogody, stawiać retencję przed nawadnianiem, zaznaczać założenia modelu. |
| Zgoda | Przed wysłaniem danych okno z informacją RODO. Bez zgody backend zwraca HTTP 403. |
| Bez klucza lub przy błędzie | Ta sama sekcja powstaje z prostych reguł, a interfejs podaje powód. |
| Oznaczenie | Raport webowy podpisuje komentarz „Analiza AI” z nazwą modelu, a wariant z reguł „Podsumowanie automatyczne (bez AI)”. |
| Konfiguracja | `AI_ENABLED`, `AI_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`. |
| Warunki | [Gemini API](https://ai.google.dev/gemini-api/terms) (bezpłatny plan z limitem, treści mogą służyć do ulepszania usług Google), [Anthropic](https://www.anthropic.com/legal/commercial-terms) (płatne za tokeny). |
| Biblioteki | `google-genai` (Apache-2.0), `anthropic` (MIT). |

Aplikacja działa w pełni bez klucza API i bez połączenia z usługą generatywnej AI.

## AI przy tworzeniu rozwiązania

| Narzędzie | Zakres |
| --- | --- |
| OpenAI Codex | Backend części B: czytanie dokumentacji, porównywanie źródeł, kod, testy, dokumentacja. |
| Claude Code (Anthropic, Claude Opus 5.5) | Mapa i wybór działek, raport webowy, PDF, integracja frontendu z backendem, dokumentacja. Część commitów ma oznaczenie `Co-Authored-By: Claude`. |
| Claude Code i Google Gemini | Podstawa frontendu, strona główna, symulator „Co jeśli?” i moduł komentarza AI. |

Narzędzia używano zgodnie z warunkami właściwymi dla kont członków zespołu
([OpenAI](https://openai.com/policies/terms-of-use/), [Anthropic](https://www.anthropic.com/legal/consumer-terms),
[Google](https://policies.google.com/terms)). Zakres zmian dokumentuje historia Git.

## Weryfikacja

Cytowane progi sprawdzono z rozporządzeniami, a wzory z literaturą podaną w metodyce.
Uruchomiono testy obliczeń i API oraz porównano wyniki KBW z obwieszczeniami MRiRW.
[Walidacja KBW](VALIDATION.md).
