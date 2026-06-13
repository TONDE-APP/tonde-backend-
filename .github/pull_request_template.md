## Description
<!-- Décris clairement ce que ce PR fait et pourquoi -->


## Type de changement
- [ ] 🐛 Bug fix
- [ ] ✨ Nouvelle feature
- [ ] ♻️ Refactoring
- [ ] 📝 Documentation
- [ ] 🔧 Configuration / DevOps
- [ ] 🧪 Tests

## Checklist avant review
- [ ] Le code respecte les conventions TONDE (async, SQLAlchemy 2.0, Pydantic v2)
- [ ] Toute logique métier est dans les services, pas dans les routers
- [ ] Toutes les requêtes DB filtrent par `org_id` (multi-tenant)
- [ ] Les tests passent : `pytest --tb=short -q`
- [ ] Pas de `print()` — utiliser `logging`
- [ ] Pas de secrets ou `.env` dans le code
- [ ] Les migrations Alembic sont incluses si un modèle a changé

## Tests effectués
<!-- Décris comment tu as testé tes changements -->


## Impact sur d'autres modules
<!-- Ce changement affecte-t-il le Queue Engine, WebSocket, ou d'autres modules ? -->


## Screenshots / logs (si applicable)
