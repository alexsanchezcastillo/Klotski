# Klotski AP2 - Memòria Tècnica

Projecte de resolució de puzzles de peces lliscants mitjançant grafs.

## Objectiu del projecte

- Construir el graf d'estats d'un puzzle Klotski.
- Trobar una solució com a seqüència de moviments.
- Analitzar propietats del graf per obtenir una puntuació d'interès.
- Interaccionar amb l'API pública per descarregar, valorar i pujar puzzles.

## Estructura del codi

- [src/puzzle.py](src/puzzle.py): tipus i validació de Puzzle, Piece i State.
- [src/logic.py](src/logic.py): simulació de moviments vàlids i aplicació de moviments.
- [src/play.py](src/play.py): joc interactiu en terminal/finestra.
- [src/image.py](src/image.py): render d'un estat en PNG.
- [src/movie.py](src/movie.py): render de la solució en GIF.
- [src/3D_view.py](src/3D_view.py): visualització 3D del graf d'estats.
- [src/download.py](src/download.py): descarrega de puzzles des del repositori.
- [src/graph.py](src/graph.py): construcció del graf d'estats i export a GraphML.
- [src/solve.py](src/solve.py): cerca del camí mínim i export de la solució a .sol.json.
- [src/eval.py](src/eval.py): avaluació d'un puzzle a partir del graf i càlcul d'una puntuació 0–5.
- [src/rate.py](src/rate.py): enviament d'una valoració al repositori via API.
- [src/generate.py](src/generate.py): generació aleatòria de puzzles nous amb filtre de qualitat.
- [src/upload.py](src/upload.py): pujada d'un puzzle nou al repositori via API.
- [src/rate_all.py](src/rate_all.py): revaloració massiva de tots els puzzles del repositori.


## Desenvolupament cronològic

Aquest apartat descriu el projecte en l'ordre real de construcció.
Cada script inclou la seva finalitat i les comandes d'ús.

### Pas 0 - Preparació de l'entorn

Instal·lació de dependències i preparació de l'entorn de treball.

```bash
pixi install
```

### Pas 1 - download.py

Primer script implementat. Connecta amb l'API pública del repositori per obtenir la llista de puzzles disponibles i descarregar-los en format JSON.

El flux és el següent:
1. GET /api/puzzles retorna una llista d'IDs (hash SHA-256 de cada puzzle).
2. Per cada ID, GET /api/puzzles/<id> retorna el puzzle en JSON.
3. Cada puzzle es valida amb Puzzle.from_json() per assegurar que el format és correcte.
4. Es desa a puzzles/<id>.json.

Permet seleccionar IDs concrets o limitar el nombre de descàrregues. Si un puzzle falla (xarxa o format invalid), el reporta pero continua amb la resta.

Per consultar IDs directament des de l'API:

```bash
# Veure tots els identificadors
curl https://klotski.pauek.dev/api/puzzles

# Veure els primers 10 identificadors, formatats
curl -s https://klotski.pauek.dev/api/puzzles | jq '.[0:10]'

# Veure només el primer identificador
curl -s https://klotski.pauek.dev/api/puzzles | jq -r '.[0]'
```

```bash
# Descarregar el top complet (fins a 100)
pixi run python src/download.py

# Descarregar només N puzzles
pixi run python src/download.py --limit 10

# Descarregar un o diversos IDs concrets
pixi run python src/download.py --id <ID>
pixi run python src/download.py --id <ID1> --id <ID2>
```

### Pas 2 - graph.py

Segon script implementat. Construeix el graf d'estats accessibles des de l'estat inicial del puzzle.

Model utilitzat:
1. Node = un estat complet del puzzle (posició de totes les peces).
2. Aresta = un moviment vàlid d'un sol pas entre dos estats.
3. Exploració BFS des de l'estat inicial fins a esgotar tots els estats accessibles.

Sortida:
- Fitxer `.graphml` per cada puzzle (per defecte amb el mateix nom del `.json`).
- El graf guarda dades de node (`state`, `is_start`, `is_goal`) i el `puzzle` original.

Comandes:

```bash
# Crear el graf amb nom de sortida per defecte (mateix que el .json)
pixi run python src/graph.py puzzles/sample3.json

# Crear el graf amb nom de sortida explícit
pixi run python src/graph.py puzzles/sample3.json puzzles/sample3.graphml
```

Nota de visualització:
- Obrir directament un `.graphml` al navegador mostra XML (text), no una imatge.
- Per veure el graf en 3D, cal executar el visor `3D_view.py`.

```bash
# Veure el graf sense camí de solució
pixi run python src/3D_view.py puzzles/sample3.graphml

# Veure el graf amb el camí de solució ressaltat (groc)
pixi run python src/3D_view.py puzzles/sample3.graphml puzzles/sample3.sol.json
```

### Pas 3 - solve.py

Tercer script implementat. Troba una solució mínima sobre el graf d'estats i la desa en format `.sol.json`.

Funcionalitat principal:
1. Carrega el puzzle.
2. Carrega el graf `.graphml` si existeix.
3. Si el graf no existeix, el construeix automàticament.
4. Busca el camí més curt des del node inicial fins a un node objectiu.
5. Converteix la seqüència d'estats a moviments `[peça, direcció]`.
6. Desa la solució en un fitxer `.sol.json`.

Comandes:

```bash
# Mode mínim: puzzle -> usa <puzzle>.graphml i desa <puzzle>.sol.json
pixi run python src/solve.py puzzles/sample3.json

# Indicant fitxer de graf explícit
pixi run python src/solve.py puzzles/sample3.json puzzles/sample3.graphml

# Indicant graf i nom de sortida de la solució
pixi run python src/solve.py puzzles/sample3.json puzzles/sample3.graphml puzzles/sample3.sol.json
```

Opcionalitats un cop generat el graph:
1. Compatible amb visualització 3D del camí:

```bash
pixi run python src/3D_view.py puzzles/sample3.graphml puzzles/sample3.sol.json
```

2. Compatible amb render de pel·lícula GIF:

```bash
pixi run python src/movie.py puzzles/sample3.json puzzles/sample3.sol.json img/sample3.gif
```

### Pas 4 - eval.py

Quart script implementat. Avalua un puzzle a partir de propietats del graf i retorna una puntuació estimada entre 0 i 5.

Base de disseny. Funcionalitats útils del graph-tool:

1. Longitud mínima de solució (`min_solution_len`):
- És la mesura principal de dificultat funcional.
- Si per resoldre calen més moviments mínims, el puzzle acostuma a ser més exigent.

2. Mida de l'espai d'estats (`nodes`, `edges`):
- Reflecteix quantes configuracions i transicions existeixen.
- Espais més grans solen donar més complexitat combinatòria.

3. Ramificació (`avg_degree`):
- Mesura quants moviments de mitjana hi ha des d'un estat.
- Indica flexibilitat local de joc.

4. Dead-ends (`dead_end_ratio`):
- Percentatge d'estats amb grau 1 (excloent start/goal).
- Massa dead-ends pot fer el graf menys ric i més lineal.

5. Clustering (`global_clustering`):
- Captura densitat local de connexions.
- Diferencia grafs molt lineals de grafs amb zones més denses.

6. Components connexos (`connected_components`):
- En el nostre flux és sobretot una comprovació (normalment 1), no la mètrica principal de dificultat.

Fórmula aplicada (heurística):

Definim $\operatorname{clamp}(x)=\min(1,\max(0,x))$ i normalitzem:

$$
L=\operatorname{clamp}\!\left(\frac{\text{min\_solution\_len}}{80}\right),\quad
S=\operatorname{clamp}\!\left(\frac{\log_{10}(\text{nodes}+1)}{5}\right),\quad
B=\operatorname{clamp}\!\left(\frac{\text{avg\_degree}}{4}\right),
$$

$$
C=\operatorname{clamp}\!\left(\frac{\text{global\_clustering}}{0.25}\right),\quad
D=\operatorname{clamp}\!\left(\frac{\text{dead\_end\_ratio}}{0.60}\right).
$$

Puntuació crua:

$$
	ext{raw}=0.45L+0.25S+0.15B+0.10C-0.10D
$$

Puntuació final (estrelles):

$$
	ext{stars}=5\cdot\operatorname{clamp}(\text{extraw})
$$

En resum: més pes per a la longitud mínima de solució, pes secundari per la mida del graf i la ramificació, i penalització suau si hi ha massa dead-ends.

Funcionalitats addicionals:

- Si no existeix el `.graphml`, el construeix automàticament.
- Mode JSON per integrar amb scripts posteriors.
- Opció `--with-betweenness` per calcular colls d'ampolla (més costós en grafs grans).

Comandes:

```bash
pixi run python src/eval.py puzzles/sample3.json
```

### Pas 5 - rate.py

Cinquè script implementat. Envia una valoració (estrelles) d'un puzzle al repositori via API.

Funcionalitat principal:
1. Rep el fitxer `.json` del puzzle i el token d'autenticació.
2. Calcula la puntuació automàticament amb `eval.py`.
3. Fa POST a `/api/puzzles/<id>/votes` amb la valoració decimal (0.0–5.0).

L'ID del puzzle és el nom del fitxer sense extensió. Si el fitxer ve de `download.py`, el nom ja és el hash SHA-256.

Comandes:

```bash
pixi run python src/rate.py puzzles/<id>.json --token <TOKEN>
```

### Pas 6 - generate.py

Sisè script implementat. Genera automàticament puzzles Klotski nous amb una puntuació de qualitat mínima garantida.

Base de disseny (per què i com):

Generació completament aleatòria rarament produeix puzzles interessants: la majoria o bé no tenen solució assolible des de l'estat inicial, o bé es resolen en un o dos moviments. Per solucionar-ho, el script combina dos filtres:

1. **Filtre ràpid (BFS limitat):** abans de construir el graf complet, es fa un BFS fins a un màxim de 8 000 nodes. Si no es troba cap estat objectiu o la solució és trivial (menys de 3 moviments), el candidat es descarta sense cost elevat.

2. **Avaluació completa (graf + mètriques):** els candidats que passen el filtre ràpid es construeixen del tot amb `graph.py` i s'avaluen amb les mètriques de `eval.py` (longitud mínima de solució, mida de l'espai d'estats, ramificació, clustering, dead-ends). El millor candidat per sobre del llindar `--min-stars` es desa.

Pipeline de generació d'un candidat:

1. Triar aleatòriament $n$ peces d'un catàleg de formes predefinides (1×1, 1×2, 2×2, L, T, S/Z, etc.).
2. Col·locar cada peça en una posició aleatòria lliure del taulell.
3. Ordenar les peces en ordre canònic (forma, posició inicial).
4. Triar la peça més gran com a peça objectiu i assignar-li una posició objectiu diferent de l'inicial.
5. Validar el puzzle amb `Puzzle.from_json` / `Puzzle.__post_init__`.

Heurística de selecció:

- Es generen fins a `--candidates` candidats vàlids (descartant els no solubles i trivials).
- De tots els avaluats, es retorna el que obté la puntuació `eval.py` més alta.
- Si cap supera `--min-stars`, el script acaba amb error i no desa res.

Comandes:

```bash
# Generar amb paràmetres per defecte (4×5, 6 peces, 10 candidats, llindar 1.5)
pixi run python src/generate.py

# Especificar dimensions i nombre de peces
pixi run python src/generate.py --width 5 --height 5 --pieces 8

# Augmentar el nombre de candidats per obtenir puzzles de més qualitat
pixi run python src/generate.py --candidates 30 --min-stars 2.5

# Reproduir un resultat concret amb llavor fixa
pixi run python src/generate.py --seed 42

# Desar en un fitxer específic
pixi run python src/generate.py --out puzzles/nou_puzzle.json
```

Sortida:

```
Candidats: 10/10 avaluats, X insolubles descartats, Y trivials descartats.
Puzzle desat a: puzzles/generated_<hash16>.json
Dimensions: 4x5
Peces: 6
Nodes del graf: ...
Longitud solució mínima: ...
Puntuació: X.XXX / 5
```

### Pas 7 - upload.py

Setè script implementat. Puja un puzzle nou al repositori col·laboratiu via API.

Funcionalitat principal:
1. Carrega el fitxer `.json` del puzzle.
2. El valida localment amb `Puzzle.from_json` per detectar errors de format abans d'enviar.
3. Fa POST a `/api/puzzles` amb el JSON del puzzle i el token d'autenticació.
4. Mostra la resposta del servidor (normalment l'ID assignat).

Notes:
- El repositori accepta fins a 200 puzzles; si s'arriba al límit, el de menys puntuació pot ser substituït aleatòriament.
- El flux recomanat és: `generate.py` → `eval.py` (verificar qualitat) → `upload.py`.

Comandes:

```bash
# Pujar un puzzle generat
pixi run python src/upload.py puzzles/generated_<hash>.json --token <TOKEN>

# Verificar el payload sense enviar
pixi run python src/upload.py puzzles/generated_<hash>.json --token <TOKEN> --dry-run
```

### Pas 8 (opcional) - rate_all.py

Vuitè script implementat (opcional). Automatitza la revaloració de tots els puzzles del repositori amb el teu criteri actual d'`eval.py`.

Funcionalitat principal:
1. Obté els IDs del top del repositori (`GET /api/puzzles`).
2. Descarrega cada puzzle si no existeix localment.
3. Calcula estrelles amb `compute_stars` (mateixa lògica que `rate.py`).
4. Envia cada vot a `POST /api/puzzles/<id>/votes`.

Comandes:

```bash
# Revalorar tots els puzzles del top
pixi run python src/rate_all.py --token <TOKEN>

# Revalorar només els primers N
pixi run python src/rate_all.py --token <TOKEN> --limit 20

# Provar sense enviar vots
pixi run python src/rate_all.py --token <TOKEN> --dry-run

# Continuar encara que algun puzzle falli
pixi run python src/rate_all.py --token <TOKEN> --continue-on-error
```

## Apèndix

### Eines de suport (visualització i validació)

No formen part del pipeline principal, però ajuden a provar i entendre resultats.

Jugar interactivament:

```bash
pixi run python src/play.py puzzles/sample1.json
```

Render d'imatge:

```bash
pixi run python src/image.py puzzles/sample1.json
```

Render GIF de la solució:

```bash
pixi run python src/movie.py puzzles/2swap.json puzzles/2swap.sol.json
```

Visualització 3D del graf:

```bash
pixi run python src/3D_view.py puzzles/2swap.graphml
pixi run python src/3D_view.py puzzles/2swap.graphml puzzles/2swap.sol.json
```


### Model de dades

Format JSON del puzzle:

```json
{
  "W": 4,
  "H": 5,
  "walls": [[x, y], ...],
  "pieces": [[[rx, ry], ...], ...],
  "start": [[x, y], ...],
  "goals": [{"i": 0, "pos": [x, y]}, ...]
}
```

- Les peces es defineixen amb coordenades relatives normalitzades (sense valors negatius).
- La posició de cada peça és la cantonada superior esquerra del rectangle contenidor.
- Un estat és la llista de posicions de totes les peces, en ordre canònic.
- Un puzzle està resolt quan es compleixen tots els objectius.

Format de moviments (.sol.json):

```json
[[piece_index, "N"], [piece_index, "E"], ...]
```

### API del repositori

Base URL: https://klotski.pauek.dev

- GET /api/puzzles: retorna IDs de puzzles.
- GET /api/puzzles/<id>: retorna puzzle + estrelles.
- POST /api/puzzles: pujada de puzzle (requereix token).
- POST /api/puzzles/<id>/votes: enviament de vot enter 0–5 (requereix token).