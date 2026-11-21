# Frontend API contract (real)

These shapes are read from `backend/app.py` and `backend/cloud.py` and were checked against a live backend. There are no guesses left.
All calls are in `src/api.js`. Every JSON error is `{error: "<message to show>", ...extra}`.
Auth is `Authorization: Bearer <token>`; a 401 clears the token and returns the user to the welcome screen.

## Errors
- `401` not signed in / expired / wrong PIN, `400` bad input, `404` unknown thing, `409` not allowed right now, `402` payment needed, `500` unexpected.
- `402` carries `action`: `"topup"` (go to the Wallet) or `"pay"` (open the unpaid invoice, with `invoice_id`). `ApiError` exposes `status`, `action`, `invoiceId`, `data`.
  The store's `run()` turns a 402 into a toast with an "Add money" or "Open invoice" button.
- `go` can also return 409 with `suggestions` (arrival battery too low).

## Auth, profile
- `GET /api/vehicles` -> `{vehicles:[{id,label,battery_kwh,max_ac_kw,max_dc_kw,ac_connector,dc_connector,wh_per_km}]}`
- `POST /api/auth/signup` `{name(2-30),pin("1234"),vehicle_model_id,soc,lat,lng}` -> 201 `{token, me}`; `POST /api/auth/login` `{name,pin}` -> `{token, me}`
- `me` = `{id,name,vehicle:{...},soc,range_km,lat,lng,wallet_balance,unpaid_invoice_id|null}`; `GET /api/me` returns `me` itself (not wrapped).
- `PATCH /api/me` `{vehicle_model_id?, soc?}` -> `me`. Only while the journey is IDLE or INVOICE, otherwise 409 ("Finish your current journey ..."). "Set battery to 15%" sends `{soc:15}`.

## Stations
- `GET /api/stations?lat&lng` -> `{stations:[station], sim_time, sim_speed}` (sorted by distance)
- station = `{id,name,lat,lng,power_cap_kw,distance_km,eta_min,arrive_soc,reachable,free_count,free_compatible,wait_estimate(min|null),chargers:[charger]}`
- charger = `{id,station_id,number,kind:'AC'|'DC',connector,max_kw,status:'AVAILABLE|RESERVED|PREPARING|CHARGING|FINISHING|FAULTED|OFFLINE',power_kw,price_base,price_now,tariff:'Peak'|'Off-peak'|'Standard',multiplier,compatible,incompatible_reason,free_in_minutes(int|null),mine}`
  - `mine` is true when I hold or use this charger (RESERVED, PREPARING, CHARGING, FINISHING). "Go now" on my own reserved charger uses it.

## Reservations
- `POST /api/reservations` `{charger_id}` -> 201 journey (state RESERVED); `DELETE /api/reservations/<id>` -> journey (IDLE, message "Reservation cancelled."). `id` is `journey.reservation.id`.

## Journey
`GET /api/journey?after=<last notice id>` -> journey. Every journey action below returns the new journey.
```
{ state: 'IDLE|RESERVED|DRIVING|ARRIVED|PLUGGED_IN|CHARGING|STOPPED|INVOICE',
  allowed_actions: [...], soc, range_km, message|null, suggestions:[...], sim_time, sim_speed, lat, lng,
  tariff:{label,multiplier}, unpaid_invoice_id|null,
  notices:[{id,kind,text}],                       // only those newer than ?after
  charger:{...charger}, station:{id,name},        // when state != IDLE
  reservation:{id, expires_in_s},                 // RESERVED, DRIVING, ARRIVED (while the hold is active)
  drive:{progress(0..1), dist_km, eta_min, arrival_soc},                          // DRIVING
  handshake:{ready, steps:[{label,done}]},                                        // ARRIVED (all pending), PLUGGED_IN
  plugged:{max_power_kw,battery_kwh,price_now,min_target,tax_percent},            // PLUGGED_IN
  charging:{power_kw,energy_kwh,soc,target_soc,elapsed_min,time_left_min|null,running_cost,spending_cap|null,rate,tariff,sharing_note,end_reason|null}, // CHARGING, STOPPED
  stopped:{reason,idle_minutes,grace_left_min,idle_fee_now,idle_fee_cap},        // STOPPED
  invoice:{...invoice} }                                                          // INVOICE
```
- `allowed_actions`: IDLE `[reserve,go,trip]`, or `[]` when an invoice is unpaid (show "Pay your invoice first", link `unpaid_invoice_id`);
  RESERVED `[go,cancel]`; ARRIVED `[plug_in]`; PLUGGED_IN `[unplug]` and `start` once `handshake.ready`; CHARGING `[stop,unplug]`; STOPPED `[unplug]`; INVOICE `[dismiss]` (+`pay` when unpaid).
- Step indicator: Reserve, Drive, Plug in, Charge, Unplug, Pay. RESERVED=0, DRIVING=1, ARRIVED=2, PLUGGED_IN=2, CHARGING=3, STOPPED=4, INVOICE=5.
- `suggestions` (after a taken charger, a fault, or an unplug) = `[{station_id,name,distance_km,free_count,arrive_soc,charger_id}]`.
- `running_cost` includes tax. `stopped.reason` / `end_reason`: `target_reached | battery_full | spending_cap | user_stop | unplugged | fault | station_offline`.
- A fault or station outage mid-session does NOT pass through STOPPED: the cable is released and the journey goes straight to INVOICE (`message` explains, `invoice.end_reason` is `fault` or `station_offline`, idle fee 0).
- Unplug with no session started goes straight to IDLE with a message and no invoice.

### Actions
- `POST /api/journey/go` `{charger_id}` (409 if the charger is taken, wrong connector, or too far for the battery)
- `POST /api/journey/plug-in` (402 `topup` if wallet < MIN_WALLET_TO_START, 402 `pay` if an invoice is unpaid). It returns at once with state PLUGGED_IN; the handshake then completes over about 2.5 s.
- `POST /api/journey/start` `{target_soc, spending_cap|null}` (409 until `handshake.ready`; target must be between `plugged.min_target` and 100; battery above 95% is refused)
- `POST /api/journey/stop`, `/unplug`, `/dismiss` (empty body)
- `POST /api/trips` `{km}` (round-trip distance) -> `{used_pct, me}`

### Notices
`notices[].kind`: `low_battery | reservation_expiring | reservation_expired | charger_taken | fault | session_complete | payment_done`.
The store sends `?after=<highest id handled>`, de-duplicates by id, and does not toast notices that already existed when the page first loaded.

## History, invoices, wallet
- `GET /api/sessions` -> `{sessions:[{id,station,charger_number,started_at,sim_started,sim_ended,energy_kwh,status:'completed'|'aborted',end_reason,total,invoice_id,invoice_status}], summary:{total_kwh,total_spend,sessions}, daily:[{date,kwh,spend}]}`
- invoice = `{id,number,session_id,energy_kwh,energy_amount,idle_fee,tax_percent,tax_amount,total,status:'paid'|'unpaid',created_at,paid_at,lines:[{label,kwh,rate,amount}],station,charger_number,vehicle,sim_started,sim_ended,end_reason,idle_minutes,session_status}`
  - `GET /api/invoices/<id>` -> invoice; `POST /api/invoices/<id>/pay` -> invoice (402 `topup` if the wallet is short). An invoice is paid from the wallet automatically at unplug when the balance covers it.
- `GET /api/wallet` -> `{balance, transactions:[{id,kind:'topup'|'payment',amount,balance_after,invoice_id,created_at}], unpaid_invoices:[invoice]}`; `POST /api/wallet/topup` `{amount}` -> same wallet shape.

## Demo tools
- `GET /api/sim/settings` -> `{speed, traffic, speeds:[1,10,20,60,120], levels:['quiet','normal','busy'], sim_time}`; `POST /api/sim/settings` `{speed?, traffic?}` -> same.
- `POST /api/sim/break-my-charger` -> journey (409 when not at a charger). A fault mid-session bills only the energy delivered.
- `GET /api/health` -> `{ok, supabase, persistent, sim_running, sim_time}`

## Client-side estimate (Ready to charge screen)
The backend has no per-percent estimate. The UI computes `kWh = (target - soc) / 100 x plugged.battery_kwh`, cost = kWh x `plugged.price_now` x (1 + `tax_percent` / 100), ignores taper and station sharing, and labels it "Estimate only, not your bill".
