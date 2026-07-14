# Myjnia AutoClean

Lokalna strona polaczona z aplikacja rezerwacji dla myjni samochodowej.

## Uruchomienie

```bash
python3 server.py
```

Nastepnie otworz:

```text
http://127.0.0.1:8000
```

## Co jest gotowe

- cennik uslug pobierany z bazy SQLite,
- logowanie z rolami wlasciciela i klienta,
- formularz rezerwacji z dodatkami, autem i danymi klienta,
- zapis rezerwacji do `database/myjnia.sqlite`,
- podglad planu pracy myjni dla wlasciciela,
- zmiana statusu wizyty przez wlasciciela,
- edycja cennika uslug i dodatkow przez wlasciciela,
- podglad wlasnych wizyt dla klienta,
- szczegoly wlasnych wizyt i odwolanie wizyty przez klienta,
- edycja profilu klienta i lista jego aut,
- formularz kontaktowy zapisujacy wiadomosci w bazie,
- lokalny asset graficzny w `web/assets/car-wash-hero.png`.

## Konta testowe

- wlasciciel: `owner@myjnia.local` / `owner123`
- klient: `anna.kowalska@example.com` / `klient123`

## Baza danych

Struktura i dane startowe sa w folderze `database`.
