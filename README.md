# maison-lavande-provence

Version statique de [www.maison-lavande-provence.fr](https://www.maison-lavande-provence.fr),
générée depuis l'ancien site WordPress (o2switch) et hébergée sur **GitHub Pages**.

- Source publiée : dossier `docs/` (branche `main`)
- Domaine personnalisé configuré via `docs/CNAME`
- `mirror.py` : script d'aspiration du site WordPress (archivé, pour régénération éventuelle)
- `cleanup.py` : script de nettoyage post-aspiration

## Formulaire de contact

Le formulaire de `docs/contact/index.html` utilise **Formspree** (gratuit).
Pour l'activer :

1. Créer un compte sur https://formspree.io
2. Créer un formulaire → récupérer l'ID (`https://formspree.io/f/XXXXXXX`)
3. Remplacer `FORM_ID_A_REMPLACER` dans `docs/contact/index.html`
4. Commit + push → déployé automatiquement

## Déploiement

GitHub Pages publie automatiquement `docs/` à chaque push sur `main`.
Settings → Pages → "Enforce HTTPS" à activer une fois le DNS basculé.
