# Changelog

## [0.2.9] - 2026-09-19

- Přidán MQTT Discovery přepínač pro společné nastavení úrovní přívodního a
  odtahového ventilátoru.
- Po zapnutí přepínače se hodnoty `Supply Air Level` zkopírují do odpovídajících
  `Return Air Level` a každá další změna se zapíše v páru.
- Po vypnutí lze úrovně přívodu a odtahu nastavovat samostatně.

## [0.2.8] - 2026-09-18

- Odstraněny vybrané EWT, postheating, kitchen hood a L1 `number` entity.
- Zbývající `number` entity používají režim `slider`.
- Odstraněné MQTT Discovery entity se při aktualizaci mažou.
- Bypass zůstává pouze jako stavová entita.

## [0.2.7] - 2026-09-18

- Rozšířen MQTT polling o dostupné údaje ComfoAir.
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

- Přidáno podrobné hex logování odeslaných a přijatých rámců.

## [0.2.3] - 2026-09-18

- Timeouty nyní obsahují příkaz a očekávanou odpověď.

## [0.2.2] - 2026-09-18

- Zlepšeno rozlišení příčin ztráty spojení ComfoAir.

## [0.2.1] - 2026-09-18

- Odstraněna závislost na předem publikovaném GHCR image.
- Home Assistant nyní sestavuje image lokálně z `build.yaml`.
