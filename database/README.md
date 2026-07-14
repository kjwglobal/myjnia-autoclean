# Baza danych strony myjni

To jest startowa baza SQLite dla strony internetowej myjni samochodowej.

## Pliki

- `schema.sql` - struktura tabel, relacje, indeksy i automatyczne daty aktualizacji.
- `seed.sql` - przykladowe uslugi, dodatki, klienci, rezerwacje i ustawienia strony.
- `myjnia.sqlite` - lokalny plik bazy danych tworzony z powyzszych plikow.

## Odtworzenie bazy

```bash
rm -f database/myjnia.sqlite
sqlite3 database/myjnia.sqlite < database/schema.sql
sqlite3 database/myjnia.sqlite < database/seed.sql
```

## Najwazniejsze tabele

- `services` - pakiety mycia i detailingu widoczne w cenniku.
- `service_addons` - dodatki do rezerwacji.
- `customers` - klienci skladajacy rezerwacje.
- `vehicles` - pojazdy przypisane do klientow.
- `bookings` - terminy wizyt.
- `booking_services` i `booking_addons` - uslugi oraz dodatki wybrane w rezerwacji.
- `payments` - platnosci za rezerwacje.
- `contact_messages` - wiadomosci z formularza kontaktowego.
- `app_users` - konta logowania z rola `owner` albo `client`.
- `site_settings` - podstawowe ustawienia strony.

## Konta demonstracyjne

- wlasciciel: `owner@myjnia.local` / `owner123`
- klient: `anna.kowalska@example.com` / `klient123`
