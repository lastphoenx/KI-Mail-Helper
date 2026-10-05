"""Synthetischer Golden Set für die Scam-Erkennung (Folder-Audit).

ALLE Absender, Domains, Personen, Nummern und Betreffs sind ERFUNDEN oder frei formuliert
(Strukturmuster, keine echten Adressen, keine echten Referenznummern). Echte Marken kommen nur als
*behauptete* Marke bzw. als legitime Großversender vor (apple.com, sbb.ch, ...).
Erfundene Domains tragen "-demo"; für Modellvergleiche optional zufällig umbenennen.

Label: S = Scam/Phishing/Betrugsspam, A = aggressiver Lead-Gen-Spam,
       N = legitimer Newsletter/Marketing, H = Ham (persönlich, System, Transaktion)
Felder: (label, anzeigename, from_adresse, betreff, provider_flag, auth, list_unsub)
  provider_flag: 1 = Provider markiert als Spam (Flag + Junk-Score), 0 = nein
  auth: 'pass' | 'none' (kein DKIM/DMARC) | 'fail'
"""
from __future__ import annotations

OWN_DOMAINS = {"meine-seite.example", "meine-firma.example"}  # Einstellung "Meine Domains"

ROWS: list = []


def _a(label, name, addr, subj, p=0, auth="pass", lu=0):
    ROWS.append((label, name, addr, subj, p, auth, lu))


def S(*a, **k):
    _a("S", *a, **k)


def A(*a, **k):
    _a("A", *a, **k)


def N(*a, **k):
    _a("N", *a, **k)


def H(*a, **k):
    _a("H", *a, **k)


# ---------- S: '/' im Local-Part (E1) ----------
S("Dr. Weber | Vitalor", "Vitalor-stoffwechsel-experten.com/guide/51827@placeholder-mail.example.org", "Diese Warnsignale Ihres Körpers sollten Sie kennen", 1, lu=1)
S("Herz Aktiv", "Herzaktiv.eu/gesundheits-partner/8kx2q@fakepost-demo.net", "Warum Abnehmen trotz Diät nicht klappt", 1, lu=1)
S("EMSense Gesundheit", "EMSense-gesundheit.com/kundenservice/30417@mailfarm-demo.fr", "Schmerzen beim Aufstehen?", 1, lu=1)
S("Löwen-Redaktion", "redaktion-loewen.de/ab3d9/71452@spamnode-demo.net", "SENSATION: Gründer überrascht die Jury", 1, lu=1)
S("Swisscom Kundenbetreuung", "Swisscom-kundenbetreuung.ch/umfrage/q8m3z@sendhost-demo.net", "Ihr Router ist abholbereit", 1, lu=1)
S("Cloud-Dienst", "Cloud-Dienst.com@wegwerf-demo.biz", "Warnung: Ihr Speicherplatz ist fast voll", 1)
S("Abnehm-Redaktion", "abnehm-redaktion.com/Mix/23871@alabastro-demo.info", "[Bericht] Was die Experten verschweigen", 1, lu=1)
S("Fit & Gesund", "fitundgesund.eu/news/9ab42@mailroute-demo.org", "Dein Körper sendet jetzt Warnzeichen", 1, lu=1)
# ---------- S: Zufalls-Local (E4) ----------
S("Secure Support", "7KQ2ZLMB@gsrem-demo.com", "Sicherheitshinweis: neue Anmeldung auf Ihrem Konto", 1)
S("No-reply", "R81TXP@dxs-demo.com", "Wichtiger Sicherheitshinweis: Identitätsprüfung erforderlich", 1)
S("No-reply", "Q9WZ3N4K@cqs-demo.com", "Handlungsbedarf: Bitte bestätigen Sie Ihre Identität", 1)
S("Reply", "B7D4FG@oyl-demo.com", "Wichtiger Hinweis zu Ihren Konto-Informationen", 1)
S("FinanceNow", "4417209385@uni-demo.ac.th", "Reduce your card debt with 0% interest for two years")
# ---------- S: Personen-Postfach + Ziffern hinter Bank/Behörden-Name (E3) ----------
S("ZKB - Zürcher Kantonalbank - Unterstutzungskontakt", "lena.fuchs58@haus-demo-allgaeu.de", "Bitte diese Angaben kurz prüfen")
S("ZKB - Zürcher Kantonalbank - Supportinformationen", "marko.weiss12@zahnarzt-demo.de", "Neue Rückmeldung vom Serviceteam", 0, "none")
S("Kantonalbank - Supportberatungshotline", "sabine.keller73@socialdemo.at", "Bitte Ihre Mitteilung kurz öffnen")
S("Kantonalbank - Kundensupport-Hotline", "tobias.brandt41@carolin-demo.de", "Neue Nachricht im Überblick")
S("Noreply", "samir.nasser004@uni-demo.ac.th", "Information zu Ihrem Abonnement")
S("SwissID Kundenbetreuung", "p.vauclair@ville-demo77.fr", "Bitte prüfen Sie die aktuelle Fassung")
S("SwissPass", "oskar.lindner@eeducation-demo.at", "SwissPass – Aktualisierung erforderlich")
# ---------- S: Homoglyphen (E5) ----------
S("Lеdgеr (ЅΑЅ)", "devicefirmwar@k4t9x2.zendesk.com", "[Security Notice] Device firmware not updated")
S("SPOTlFY Music", "store+55102938475@g.shopifyemail.com", "Aktualisierung Ihres Kundenkontos erforderlich", 1, lu=1)
# ---------- S: behauptete Marke ≠ Domain (nur Marken-/KI-Wissen hilft) ----------
S("Raiffeisen Kundenservice", "kv02@devs-demo-template.com", "Ein wichtiger Hinweis zu Ihrem Konto, Ref:00000000")
S("BCV Banque - Service client", "info@duo-demo-design.ch", "vérification de votre identité", 0, "none")
S("Helsana AG", "push-demo@waat-demo.com", "Mögliche Rückerstattung: 180 CHF", 1)
S("SBB swiss", "website@amaji-demo.com", "Zahlungsaufforderung Rechnung SBB-0000-0000", 1)
S("Deutsche Telekom", "Deutsche-Telekom@sufac-demo.com", "60% Rabatt aktiviert – Ihr Code ist bereit", 1)
S("dm-drogerie markt", "dm-Kundenservice@factoria-demo.fr", "Ihr Gutscheincode ist freigeschaltet", 1)
S("ADAC Umfrage-Insider", "ADAC@spacepos-demo.net", "ADAC: Eine besondere Überraschung wartet", 1)
S("Deutschlandticket Team", "Deutschlandticket@ihouzz-demo.com", "LETZTE CHANCE: Ihr Gewinn wartet", 1)
S("Migros", "migros.qwxzvt@migros-kunst-demo.de", "Erhalten Sie Ihre gratis Lebensmittelbox")
S("FedEx Kundendienst", "FedEx-Kundendienst.team@artisti-demo.org", "Letzte Aufforderung: Sofortige Antwort erforderlich", 1, lu=1)
S("Doctolib Support", "Doctolib-support@resend.dev", "Ihr Gesundheits-Set wartet noch", 1)
S("Doctolib Support", "support.doctolib@buildabiz-demo.com", "Erinnerung an Ihr Gesundheits-Set", 1)
S("Digitec Kundenservice", "hp.intch@comeinwash-demo.co.kr", "Premium-Laptop: nur wenige Minuten Zeit", 1)
S("Parking-Pay", "or=beispielfirma.com@c.havemy-demo.email", "Parkticket - Zahlung offen", 1, lu=1)
S("HubSpot Data Privacy", "hello@hubspot-glued-phish.example", "Notice about processing of personal data")
S("PostFinance Sicherheit", "service@postfinance-secure-demo.com", "Ihr Konto wurde gesperrt", 1)
S("TWINT", "info@twint-verify-demo.net", "TWINT: Bitte bestätigen Sie Ihre Zahlung", 1)
S("UBS Kundendienst", "ubs.kunden@mailhost-demo.ru", "Wichtig: Sicherheitsupdate für Ihr E-Banking", 1)
# ---------- S: kompromittierte echte Postfächer / Behörden-Fake ----------
S("Admin- @POLIZEI", "m.demo@netplus-demo.ch", "Fwd: Re: OFFIZIELLER BERICHT ZUM VERSTOSS")
S("Noreply", "x7q_demo@szes-demo.cz", "Information zu Ihrem Abonnement")
S("Support-Team", "timo.demo@premium-demo.example", "Ihr Premium-Abonnement: Erneuerung steht an")
S("Mr. Jeffrey Demo", "info@techvc-demo.org", "Wichtige Fördermöglichkeit für finanzielle Unterstützung", 1)
S("Plazner HR", "info@reteteu-demo.com.br", "Wir haben Ihre Anfrage erhalten.", 1, lu=1)
S("Maria Von Demo", "maria.von.demo@proagent-demo.com", "Ihr Paket wurde versandt!", 1, lu=1)
S("Noreply", "mu.demo@student.demo-college.ac.zw", "Renew Your Subscription", 1)
S("The Demo Foundation", "admin1@phoenix-demo-yoga.com", "Wichtig! / Importante!", 1)
S("Amendes.ch", "newslettre@proyecta-demo.com", "Nouveau document disponible : amende", 1, lu=1)
S("noreply", "postmaster@cc-demo-academy.am", "Dieses Angebot läuft bald aus.", 1)
S("Enora Demo", "enora.demo@umpv-demo.fr", "Prise de contact", 1)
S("mk-demo", "mk-demo@alfaris-demo.com", "(Kein Betreff)", 1)
S("myShop", "store+55102938476@g.shopifyemail.com", "Bestätigung Ihrer Rückerstattung – CHF 300.00", 1, lu=1)
S("Promo-Demo", "mail@promo-demo-girls.com", "hast du das schon gesehen?")
# ---------- A: aggressiver Lead-Gen-Spam (echte Marken über fremde Versender) ----------
A("Solar Demo / Immobilienpreise", "send@hub.leadnetz-demo.de", "Solaranlage: Komplettpreis inkl. Montage", 1, lu=1)
A("Finanzierung Online", "send@infos.leadnetz-demo.de", "Sichern Sie sich jetzt Ihre Wunschfinanzierung", 1, lu=1)
A("Gewinnspiel Aktion", "send@newsletter.shoppinginfo-demo.com", "Millionen-Gewinne garantiert – die Herbst-Chance", 1, lu=1)
A("Kredit Aktuell", "send@newsletter.selecto-demo.de", "Jetzt Wunschkredit sichern", 1, lu=1)
A("Immobilienprofi", "send@mails.select-demo.de", "Kostenloser Marktwert-Report für Ihre Immobilie", 1, lu=1)
# ---------- N: legitime Newsletter (nur große, allgemein bekannte Versender + erfundene) ----------
N("Digitec", "news@newsletter.digitec.ch", "Neu im Sortiment: Produkte der Woche", lu=1)
N("Galaxus", "noreply@productnews.galaxus.ch", "Ein Artikel ist wieder lieferbar", lu=1)
N("SBB Newsletter", "mailings@mailings.sbb.ch", "Aktion: Tageskarte für 2.", lu=1)
N("Apple", "News@InsideApple.Apple.com", "Hier eine Zusammenfassung der neuesten Ankündigungen", lu=1)
N("Amazon.de", "promotion5@amazon.de", "Aktionen der Woche", lu=1)
N("Instagram", "posts-recap@mail.instagram.com", "Sieh dir an, was es Neues gibt", lu=1)
N("LinkedIn", "messages-noreply@linkedin.com", "Neue Kontaktanfragen für dich", lu=1)
N("Lenovo", "lenovo@ecomm.lenovo.com", "Neue Angebote für Sie ausgewählt", lu=1)
N("UBS Switzerland AG", "ubs_switzerland@mailing.ubs.com", "Markt in Kürze", lu=1)
N("Volkswagen", "news@mail.volkswagen.ch", "Neuer Elektro-Kleinwagen: jetzt Probe fahren", lu=1)
N("Versand Muster", "sales@notice.versand-muster-demo.com", "Neue Produkte jetzt auf Lager")
N("Reisebüro Muster", "mail@mailing.reisebuero-muster-demo.ch", "Erhalten Sie einen Bonus auf alle Reisen", lu=1)
N("Schuhhaus Muster Club", "club@club.schuhhaus-muster-demo.ch", "Sunday Deal: 25% auf ausgewählte Marken", lu=1)
N("TV Muster", "noreply@email.tv-muster-demo.ch", "Ein Anbieter. Eine Rechnung. Alles drin.", lu=1)
N("Baumarkt Muster", "newsletter@info.baumarkt-muster-demo.ch", "-20% extra: Profiwochen für Heimwerker", lu=1)
N("Elektrohandel Muster", "infomail@info.elektrohandel-muster-demo.ch", "Neuheiten jetzt entdecken", lu=1)
N("Naturschutz Muster", "info@naturschutz-muster-demo.org", "Aktuelles aus der Natur", lu=1)
N("Sprachkurs Muster", "newsletter@news.sprachkurs-muster-demo.de", "Neue Lernthemen für Anfänger", lu=1)
N("Schokolade Muster", "kunden@newsletter.schokolade-muster-demo.ch", "Neu entdecken: die Frühlings-Kollektion", lu=1)
N("Magazin Muster+", "plus@newsletter.magazin-muster-demo.de", "Update: die Themen der Woche", lu=1)
# legitime Newsletter, die der Provider fälschlich flaggt (Falschalarm-Quelle!)
N("Beispiel Games", "communications@beispielgames-demo.info", "We're Publishing a New Story-Driven RTS", 1, lu=1)
N("Fotoapp Team", "team@info.fotoapp-demo.com", "Neue Funktionen für deine Fotos", 1, lu=1)
N("Optiker Muster", "news@e.optiker-muster-demo.ch", "Schützen Sie Ihre Augen vor dem Bildschirm.", 1, lu=1)
N("Fotoservice Muster", "noreply@fotoservice-demo.ch", "Bis zu 25 % Sommerrabatt im Fotoservice!", 1, lu=1)
N("Analytics Demo", "noreply@analytics-demo.org", "Version 5.8.0 ist da", 1, lu=1)
N("Paketdienst Demo", "newsletter@chnews.paketdienst-demo.com", "Feiertags-Öffnungszeiten", 1, lu=1)
N("Spiele Demo Release", "info@spiele-demo.com", "Release version 12.0.76 now available", 1, lu=1)
N("Treuhand Muster AG", "transparent@muster-treuhand.ch", "Aktuelle Informationen der Treuhand", 1, lu=1)
N("survey@shop-demo.ch via SurveyMonkey", "member@surveymonkeyuser.com", "Wie war Ihr letzter Kontakt mit uns?", 1, lu=1)
N("Terminal App News", "no-reply_at_news_terminalapp_com_abc123_3e11@privaterelay.appleid.com", "Terminal App: neue Updates")
N("Muster IT | Apple Premium Reseller", "noreply@muster-it.ch", "25% Rabatt auf das gesamte Sortiment", lu=1)
# ---------- H: Ham ----------
H("WordPress", "wordpress@meine-seite.example", "[Wordfence Alert] Problems found on meine-seite.example", 1, "none")
H("WordPress", "wordpress@meine-firma.example", "Ihre Website wurde auf WordPress 7.1.2 aktualisiert", 0, "none")
H("root", "root@meine-firma.example", "Rsync erfolgreich: von /data nach backup")
H("NAS-Monitor", "monitor@meine-firma.example", "[NAS] 1 neue verdächtige Datei(en)", 1)
H("UniFi Network", "unifi@meine-firma.example", "Console Backup Created", 1)
H("Anna Muster", "anna.muster@example-freemail.ch", "Fwd: Angebot", 1)
H("Beat Beispiel", "beat.beispiel@example-firma.ch", "AW: Jahresrechnung 2026")
H("Castelli, Marco", "marco.castelli@kantonalbank-demo.ch", "Besprechung nächste Woche")
H("Meier Elektro AG", "hans.meier@meier-elektro.ch", "Schlussrechnung Projekt 2026")
H("Muster Treuhand AG", "claudia.muster@muster-treuhand.ch", "Steuerunterlagen 2025")
H("Praxis Muster", "praxis.muster@hin.ch", "AW: Terminbestätigung")
H("Gemeinde Beispiel", "sachbearbeiter@gemeinde-beispiel.ch", "AW: Ihre Anfrage")
H("Studio Rossi", "c.rossi@studio-rossi.it", "R: Saldo offene Posten")
H("Apple", "no_reply@email.apple.com", "Deine Rechnung von Apple", lu=0)
H("Apple", "noreply@email.apple.com", "Dein Apple Account wurde verwendet, um sich bei iCloud anzumelden")
H("Post CH AG - Info Sendungsstatus", "notifications@post.ch", "Unterwegs: Paket von Beispiel AG")
H("Webhosting Muster", "billing@webhosting-muster-demo.ch", "Rechnung verfügbar")
H("LastPass", "do-not-reply@mail.lastpass.com", "LastPass Security Notification: Login attempt blocked")
H("PayPal", "service@paypal.ch", "Sie haben eine Zahlung erhalten")
H("Onlineshop Muster", "bestellung@onlineshop-muster-demo.de", "Bestellt: Artikel")
H("Fitnessclub Muster", "no-reply@email.fitnessclub-muster-demo.ch", "Zahlungserinnerung – Bitte begleichen Sie Ihre Zahlung")
H("Zeitschrift Muster", "leserservice@zeitschrift-muster-demo.de", "Ihr Abo - Mahnung")
H("Versicherung Beispiel", "vertrag@versicherung-beispiel.ch", "Automatic reply: Jahresrechnungen", 0, "fail")
H("Energie Italia", "clienti@energia-demo.it", "SERVIZIO CLIENTI [000000]", 1, "fail")
H("Elektrohandel Muster", "noreply@elektrohandel-muster-demo.ch", "Dein Servicefall ist erfasst")
H("Shop Muster", "bestellung@orders.shop-muster-demo.com", "Die Bestellung wurde versandt")
H("Familie", "kontakt@example-freemail.ch", "Fotos", 1)
H("Frieda Beispiel", "frieda.beispiel@hotmail.com", "Rechnung 2026 R-0000123")
H("Praxis Dr. Muster", "praxis@hin.ch", "Unterlagen")
H("Bank Beispiel", "andreas.castelli@kantonalbank-demo.ch", "Besprechung nächste Woche", 0, "pass")
H("SwissID", "no-reply@swissid.ch", "Anmeldung mit Chrome auf Mac OS festgestellt")
H("Raiffeisen", "noreply@raiffeisen.ch", "Ihr E-Banking Vertrag")
H("Zürcher Kantonalbank", "info@zkb.ch", "Ihre Kontoübersicht")
H("TWINT", "service@twint.ch", "Ihre TWINT Zahlung")
H("Swisscom", "noreply@swisscom.com", "Ihre Rechnung ist da")
H("Helsana", "service@helsana.ch", "Ihr Auszug für die Steuererklärung")
H("Migros", "info@migros.ch", "Ihre Bestellung bei Migros Online")
H("Stefan Beispiel", "s.beispiel@uni-beispiel.ch", "training")
