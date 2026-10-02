# ⚙️ Maintenance Prédictive Industrielle

*Voir la panne avant qu'elle arrive.*

Application Streamlit basée sur le dataset **AI4I 2020** (10 000 machines).

## Fonctionnalités
- Page de connexion (login / mot de passe) avec fond personnalisé
- Dashboard : 6 KPI + graphiques Plotly
- **Inspection machine** : schéma de la machine avec la zone en cause qui clignote (outil, broche, moteur, refroidissement) et le diagnostic
- **Alertes** : score de risque par machine, bandeau animé et onglet dédié pour les machines proches de la panne
- Filtres interactifs (qualité, statut, cause, rpm, couple, usure)
- Analyse approfondie (histogrammes, corrélation, sunburst, 3D)
- Saisie de nouvelles mesures → KPI et graphiques mis à jour automatiquement
- Export CSV

## Gestion et échanges (ajouts)
- **Maintenance** : planning Kanban (À faire / En cours / Fait, responsable, date), historique d'une machine avec courbe, calcul coûts/gains, comparaison de deux machines
- **Rapports & échanges** : rapport PDF + Excel, import CSV/Excel, QR code par machine (`?machine=ID`) et planche d'étiquettes
- **Notifications** : alertes Email (SMTP) et Telegram via les secrets (`[email]`, `[telegram]`)
- **Mode écran atelier** (bouton dans la barre latérale) : affichage plein écran, rafraîchi toutes les 30 s
- **Carte de l'usine**, **mode sombre / clair**, **3 langues** (FR / AR / EN)

## Activer les alertes Email (Gmail) et Telegram
Le plus simple : onglet **Notifications** dans l'application → remplis le formulaire → **Enregistrer et tester**.
Les identifiants sont gardés dans `settings.json` (ignoré par git). Alternatives : `.env` (voir `.env.example`) ou `.streamlit/secrets.toml`.
- **Gmail** : active la validation en 2 étapes puis crée un *mot de passe d'application* sur https://myaccount.google.com/apppasswords (pas ton mot de passe normal).
- **Telegram** : @BotFather → `/newbot` → copie le token → ouvre ton bot, appuie sur START → bouton « Trouver mon chat_id ».

## Sauvegarde des données
Planning → `tasks.csv`, historique → `history.csv`, nouvelles saisies → `ai4i2020_live.csv`. Écriture atomique ; un avertissement s'affiche si la sauvegarde échoue.

## Contenu du dossier
- `i18n.py` : toutes les traductions · `extras.py` : écrans de gestion · `reports.py` : PDF/Excel/QR · `notify.py` : Email/Telegram
- `app.py` : l'application
- `assets/` : logo, icônes et fonds d'écran (générés par `tools/make_assets.py`)
- `.streamlit/config.toml` : thème (couleurs)
- `.streamlit/secrets.toml.example` : modèle pour les mots de passe
- `ai4i2020.csv` : les données

## Lancer en local (Windows : double-clic sur `lancer.bat`)
```bash
pip install -r requirements.txt
streamlit run app.py
```
Le compte par défaut est défini dans `app.py` (`DEFAULT_USERS`, mot de passe stocké sous forme d'empreinte SHA-256).
Pour changer d'identifiants, utilise `.streamlit/secrets.toml` (voir l'exemple).

## Changer le nom, les couleurs ou le logo
- **Nom / slogan** : en haut de `app.py` (`APP_NAME`, `APP_TAGLINE`).
- **Couleurs** : `INK`, `COPPER`, `TEAL`… dans `app.py` et `tools/make_assets.py`.
- **Logo, icônes, fonds** : modifie `tools/make_assets.py` puis lance `python tools/make_assets.py`,
  ou remplace directement les fichiers de `assets/` par les tiens (même noms : `logo.png`, `bg_login.jpg`, `bg_hero.jpg`).

## Déployer sur Streamlit Community Cloud
1. Crée un dépôt GitHub avec le contenu de ce dossier (`app.py`, `i18n.py`, `extras.py`, `reports.py`, `notify.py`, `requirements.txt`, `ai4i2020.csv`, `assets/`, `.streamlit/config.toml`).
2. Va sur https://share.streamlit.io → **New app** → choisis le dépôt, la branche et `app.py`.
3. (Recommandé) **Settings → Secrets** : copie le contenu de `.streamlit/secrets.toml.example` avec tes propres mots de passe.
4. **Deploy** puis copie le lien public.

> ⚠️ Sur Streamlit Cloud, le disque est temporaire : les nouvelles saisies restent pendant la session et peuvent disparaître au redémarrage de l'app. Pour une persistance réelle, branche une base (Google Sheets, Supabase, SQLite hébergé…).
