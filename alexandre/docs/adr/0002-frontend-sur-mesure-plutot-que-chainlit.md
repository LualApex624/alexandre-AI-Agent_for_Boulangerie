# ADR-0002 : Une interface sur mesure (FastAPI + WebSocket) plutôt que Chainlit

**Date** : 2026-11-09
**Statut** : accepté
**Décideurs** : Paul-Alex Yao

## Contexte

Le cahier des charges (§9) retient Chainlit. Une maquette d'interface a ensuite été produite (« Alexandre — assistant de boulangerie ») : palette boulangerie (Farine, Dorure, Croûte, Four, Levain), typographies Fraunces et DM Sans, un personnage animé dont l'humeur montre si l'assistant est au repos, en train de travailler ou prêt, des cartes riches (stock, prévision) et une alerte proactive. Chainlit permet de restyler et d'insérer des composants dans les messages, mais pas de maîtriser l'en-tête, la zone de saisie ni l'animation du personnage selon l'état de l'agent.

## Décision

Alexandre a sa propre interface : une page HTML/CSS/JS sans framework, servie par **FastAPI**, qui dialogue avec l'agent par **WebSocket**. L'agent, les outils, la validation des commandes et les évaluations ne changent pas : l'interface s'appuie sur la même classe `Conversation`. Les exigences du §9 sont conservées : langue française, thème clair, appels d'outils visibles, 3 à 4 suggestions, nom et avatar.

## Alternatives considérées

### Chainlit restylé (CSS, thème, `cl.CustomElement`)
- **Pour** : conforme au cahier, peu de code, sécurité de transport fournie.
- **Contre** : en-tête et zone de saisie imposés ; pas d'avatar dont l'humeur suit l'état de l'agent ; rendu éloigné de la maquette.
- **Pourquoi pas** : la maquette fait de l'humeur du personnage un élément central de l'expérience (Madeleine doit voir si Alexandre l'écoute, travaille ou a fini).

### Framework front (React, Vue…)
- **Pour** : composants, écosystème.
- **Contre** : chaîne de build (Node), dépendances supplémentaires, installation plus longue pour un tiers.
- **Pourquoi pas** : une seule page, quelques composants ; le JavaScript natif suffit et garde le démarrage en moins de 15 minutes (§12).

## Conséquences

### Positives
- Interface fidèle à la maquette, mobile d'abord, personnage animé selon l'état réel de l'agent.
- Les cartes affichent uniquement des chiffres issus des résultats d'outils (règle « aucun chiffre inventé »).
- Une dépendance lourde en moins (Chainlit).

### Négatives
- Écart assumé au §9 du cahier des charges, à expliquer en restitution.
- Ce que Chainlit fournissait est désormais à notre charge : WebSocket, contrôle de l'origine des connexions, en-têtes de sécurité (CSP), rendu sûr du texte, reconnexion.

### Risques
- **Faille côté navigateur (XSS, détournement de WebSocket)** : aucun texte n'est inséré comme HTML, origine vérifiée à la connexion, CSP stricte, serveur limité à `127.0.0.1` ; couvert par des tests.
- **Dérive entre l'interface et l'agent** : le protocole WebSocket est documenté dans le README et testé de bout en bout avec un modèle scripté.
