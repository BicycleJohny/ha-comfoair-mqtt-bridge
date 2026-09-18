# Changelog

Všechny významné změny tohoto projektu jsou uvedeny v tomto souboru.

## [0.2.8] - 2026-09-18

- Odstraněny nepoužívané `number` entity:
  - EWT High Temperature
  - EWT Low Temperature
  - EWT Speed Up
  - Extractor Hood Switch Off Delay Minutes
  - Kitchen Hood Speed Up
  - L1 Switch Off Delay Minutes
  - Postheating Target Temperature
- Zbývající `number` entity používají MQTT Discovery režim `slider`.
- Odstraněné entity se při aktualizaci automaticky smažou z MQTT Discovery.
- Bypass zůstává pouze jako stavová entita, protože pro jeho nucenou aktivaci není
  k dispozici ověřený příkaz protokolu.
- Doplněna dokumentace k omezením lokalizace MQTT Discovery.

## [0.2.7] - 2026-09-18

- Rozšířen MQTT polling o dostupné údaje ComfoAir:
  - otáčky a výkon ventilátorů,
  - provozní hodiny,
  - časové prodlevy,
  - fyzické vstupy a analogové vstupy,
  - bypass, předehřev, enthalpie a EWT/post-heating,
  - diagnostika chyb.
- Přidány MQTT Discovery entity typu `sensor`, `binary_sensor`, `number` a
  `button`.
- Přidány příkazy pro procenta ventilátorů, časové prodlevy, EWT/post-heating a
  reset chyb.

## [0.2.6] - 2026-09-18

- MQTT `climate` entity doplněna o aktuální teplotu vratného vzduchu.
- Nastavena přesnost teploty na 0,5 °C.

## [0.2.5] - 2026-09-18

- Přidáno MQTT Discovery tlačítko pro reset filtru.

## [0.2.4] - 2026-09-18

- Přidáno podrobné hex logování odeslaných a přijatých RS232/TCP rámců.

## [0.2.3] - 2026-09-18

- Timeouty při čekání na odpověď nyní obsahují příkaz a očekávanou odpověď.

## [0.2.2] - 2026-09-18

- Zlepšeno rozlišení příčin ztráty spojení ComfoAir.

## [0.2.1] - 2026-09-18

- Odstraněna závislost na předem publikovaném GHCR image.
- Home Assistant nyní sestavuje image lokálně z `build.yaml`.
