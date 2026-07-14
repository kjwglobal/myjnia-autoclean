PRAGMA foreign_keys = ON;

INSERT INTO services (name, slug, description, duration_minutes, base_price_pln, display_order)
VALUES
  ('Mycie podstawowe', 'mycie-podstawowe', 'Szybkie mycie zewnetrzne z osuszeniem karoserii.', 30, 39.00, 1),
  ('Mycie premium', 'mycie-premium', 'Mycie zewnetrzne, odkurzanie wnetrza i czyszczenie szyb.', 60, 89.00, 2),
  ('Detailing wnetrza', 'detailing-wnetrza', 'Dokladne czyszczenie kokpitu, tapicerki, dywanikow i bagaznika.', 120, 199.00, 3),
  ('Woskowanie', 'woskowanie', 'Ochronne woskowanie lakieru po myciu zewnetrznym.', 90, 149.00, 4);

INSERT INTO service_addons (name, description, duration_minutes, price_pln)
VALUES
  ('Pranie tapicerki fotela', 'Czyszczenie jednego fotela metoda ekstrakcyjna.', 20, 35.00),
  ('Czyszczenie felg', 'Dokladne doczyszczenie felg i nadkoli.', 15, 25.00),
  ('Ozonowanie', 'Odgrzybianie i neutralizacja zapachow we wnetrzu auta.', 30, 59.00),
  ('Usuniecie owadow i smoly', 'Dodatkowe czyszczenie trudnych zabrudzen z karoserii.', 20, 45.00);

INSERT INTO customers (first_name, last_name, email, phone, marketing_consent)
VALUES
  ('Anna', 'Kowalska', 'anna.kowalska@example.com', '+48 501 222 333', 1),
  ('Piotr', 'Nowak', 'piotr.nowak@example.com', '+48 602 333 444', 0);

INSERT INTO vehicles (customer_id, registration_number, brand, model, vehicle_size, color)
VALUES
  (1, 'WA12345', 'Toyota', 'Corolla', 'standard', 'bialy'),
  (2, 'KR98765', 'Skoda', 'Kodiaq', 'suv', 'grafitowy');

INSERT INTO bookings (
  customer_id,
  vehicle_id,
  starts_at,
  ends_at,
  status,
  total_price_pln,
  customer_notes
)
VALUES
  (1, 1, '2026-06-22 10:00:00', '2026-06-22 11:00:00', 'confirmed', 114.00, 'Prosze o dokladne wyczyszczenie szyb.'),
  (2, 2, '2026-06-23 14:00:00', '2026-06-23 16:30:00', 'new', 258.00, NULL);

INSERT INTO booking_services (booking_id, service_id, price_pln)
VALUES
  (1, 2, 89.00),
  (2, 3, 199.00);

INSERT INTO booking_addons (booking_id, addon_id, price_pln)
VALUES
  (1, 2, 25.00),
  (2, 3, 59.00);

INSERT INTO payments (booking_id, amount_pln, method, status, paid_at)
VALUES
  (1, 114.00, 'card', 'paid', '2026-06-20 12:30:00'),
  (2, 258.00, 'cash', 'pending', NULL);

INSERT INTO contact_messages (name, email, phone, subject, message)
VALUES
  ('Marek Zielinski', 'marek.zielinski@example.com', '+48 700 111 222', 'Pytanie o pranie tapicerki', 'Czy moge umowic pranie calej tapicerki na sobote?');

INSERT INTO app_users (name, email, phone, password_hash, role, customer_id)
VALUES
  (
    'Wlasciciel AutoClean',
    'owner@myjnia.local',
    '+48 123 456 789',
    'pbkdf2_sha256$260000$IJtUaFivpb4Lygc88PoUVg==$thVrkWHagdEar7kDVhDRpMcAhHT9VBILcjDeWYb9pGs=',
    'owner',
    NULL
  ),
  (
    'Anna Kowalska',
    'anna.kowalska@example.com',
    '+48 501 222 333',
    'pbkdf2_sha256$260000$mES2IzB1tVPQJVGEuVI8Jg==$gTyoggBXDH1A6y9g2nfBCjyIPFdVz0rdxUmds5W0izM=',
    'client',
    1
  );

INSERT INTO site_settings (key, value)
VALUES
  ('business_name', 'Myjnia AutoClean'),
  ('business_phone', '+48 123 456 789'),
  ('business_email', 'kontakt@myjnia.local'),
  ('business_address', 'ul. Przykladowa 1, 00-001 Warszawa'),
  ('opening_hours', 'Pon-Pt 08:00-18:00; Sob 09:00-15:00'),
  ('station_count', '1');

INSERT INTO business_hours (weekday, is_open, opens_at, closes_at)
VALUES
  (0, 1, '08:00', '18:00'),
  (1, 1, '08:00', '18:00'),
  (2, 1, '08:00', '18:00'),
  (3, 1, '08:00', '18:00'),
  (4, 1, '08:00', '18:00'),
  (5, 1, '09:00', '15:00'),
  (6, 0, '09:00', '15:00');

INSERT INTO client_notifications (
  customer_id,
  booking_id,
  type,
  title,
  message,
  is_read
)
VALUES
  (
    1,
    1,
    'booking_status',
    'Wizyta potwierdzona',
    'Twoja wizyta z 2026-06-22 10:00 ma status: potwierdzona.',
    0
  );
