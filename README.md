# Klotski AP2 - Memòria Tècnica

Projecte de resolució de puzzles de peces lliscants mitjançant grafs.
L'objectiu principal és modelar l'espai d'estats d'un puzzle, trobar solucions mínimes i avaluar l'interès dels puzzles per contribuir al repositori col·laboratiu.

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
- [src/eval.py](src/eval.py): avaluació heurística v2 (0–5 estrelles) amb desglossament `score_terms`.
- [src/rate.py](src/rate.py): enviament de la valoració calculada per `eval.py` al repositori via API.

## Model de dades

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

Criteris clau:

- Les peces es defineixen amb coordenades relatives normalitzades (sense valors negatius).
- La posició de cada peça és la cantonada superior esquerra del rectangle contenidor.
- Un estat és la llista de posicions de totes les peces, en ordre canònic.
- Un puzzle està resolt quan es compleixen tots els objectius.

Format de moviments (.sol.json):

```json
[[piece_index, "N"], [piece_index, "E"], ...]
```

## API del repositori

Base URL: https://klotski.pauek.dev

- GET /api/puzzles: retorna IDs de puzzles.
- GET /api/puzzles/<id>: retorna puzzle + estrelles.
- POST /api/puzzles: pujada de puzzle (requereix token).
- POST /api/puzzles/<id>/votes: enviament de vot enter 0–5 (requereix token).

## Desenvolupament cronològic (apartat principal)

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
4. Es desa a puzzles/<id>.json amb indentació per facilitar la lectura.

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

# Triar carpeta de sortida
pixi run python src/download.py --limit 10 --out altra_carpeta
```

### Pas 2 - graph.py

Segon script implementat. Construeix el graf d'estats accessibles des de l'estat inicial del puzzle.

Model utilitzat:
1. Node = un estat complet del puzzle (posició de totes les peces).
2. Aresta = un moviment vàlid d'un sol pas entre dos estats.
3. Exploració BFS des de l'estat inicial fins a esgotar tots els estats accessibles.

Sortida:
- Fitxer `.graphml` per cada puzzle (per defecte amb el mateix nom del `.json`).
- El graf guarda metadades de node (`state`, `is_start`, `is_goal`) i el `puzzle` original.

Comandes:

```bash
# Crear el graf amb nom de sortida per defecte
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

Validació feta:
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

**Heurística v2** (implementada a `compute_metrics` + `compute_score_terms` + `score_from_metrics`):

Objectiu: no premiar només puzzles «grans i llargs», sinó puzzles amb **estructura** (fases, colls d'ampolla), **dificultat real** i sense ser **trivials**.

#### Mètriques calculades

| Mètrica | Descripció |
|---------|------------|
| `solvable` | Si algun objectiu és accessible des de l'inicial |
| `min_solution_len` | Distància mínima start → goal (−1 si no resoluble) |
| `path_density` | `min_solution_len / log₁₀(nodes + 1)` |
| `nodes`, `edges`, `avg_degree` | Mida i ramificació del graf |
| `dead_end_ratio` | Proporció d'estats amb grau 1 (excloent start/goal) |
| `global_clustering` | Densitat local de connexions |
| `max_vertex_betweenness` | Coll d'ampolla principal (sempre calculat) |
| `connected_components` | Validació estructural (normalment 1) |

#### Termes de puntuació (0–1)

Definim $\operatorname{clamp}(x)=\min(1,\max(0,x))$:

- **Dificultat** $L = \operatorname{clamp}(\frac{\text{min\_len}}{80}) \cdot \operatorname{clamp}(\frac{\text{min\_len}}{10})$
- **Mida** $S = \operatorname{clamp}(\frac{\log_{10}(n+1)}{5}) \cdot \operatorname{clamp}(\frac{n}{50})$
- **Densitat del camí** $P = \operatorname{clamp}(\frac{\text{path\_density}}{8})$
- **Coll d'ampolla** $K = \operatorname{clamp}(\frac{\text{max\_vertex\_betweenness}}{0.15 \cdot n})$
- **Ramificació** (banda mitjana al volt de 2.8): $R = \operatorname{clamp}(1 - \frac{|\text{avg\_degree} - 2.8|}{2.8})$
- **Clustering** $C = \operatorname{clamp}(\frac{\text{global\_clustering}}{0.25})$
- **Penalització dead-ends** $D = \operatorname{clamp}(\frac{\text{dead\_end\_ratio}}{0.60})$
- **Penalització trivial** $T$: combina solució curta (&lt; 10 movs) i graf petit (&lt; 50 nodes)

Si `solvable` és fals → **0 estrelles**.

Puntuació crua:

$$
\text{raw} = 0.35L + 0.15P + 0.15K + 0.15R + 0.15S + 0.05C - 0.15D - 0.10T
$$

$$
\text{stars} = 5 \cdot \operatorname{clamp}(\text{raw})
$$

La sortida inclou `score_terms` (desglossament) amb `--json`.

#### Per què és millor que la v1

- **Betweenness** integrada → detecta fases i ponts estrets.
- **Sòls mínims** → evita 4–5 estrelles a puzzles minúsculs.
- **Densitat del camí** → no premia només molts nodes sense relació amb la solució.
- **Ramificació en banda** → evita grafos caòtics o purament lineals.
- **Resolubilitat** → 0 estrelles si el puzzle no es pot resoldre.

Funcionalitats:

- Construcció automàtica del `.graphml` si no existeix.
- `--json`: sortida amb mètriques, `score_terms` i `stars`.
- `--with-betweenness`: afegeix `max_edge_betweenness` (la de vèrtexs ja entra a la nota).

Comandes:

```bash
# Avaluació textual amb desglossament
pixi run python src/eval.py puzzles/sample3.json

# Sortida JSON (per comparar puzzles)
pixi run python src/eval.py src/puzzles/<id>.json --json

# Puzzles descarregats del repositori
pixi run python src/eval.py src/puzzles/<id>.json --json
```

### Pas 5 - rate.py

Cinquè script implementat. Envia una valoració (estrelles) d'un puzzle al repositori via API.

Funcionalitat principal:
1. Rep el fitxer `.json` del puzzle i el token d'autenticació.
2. Calcula la puntuació amb la **mateixa heurística v2** que `eval.py`.
3. Fa POST a `/api/puzzles/<id>/votes` amb `stars` en decimal (0.0–5.0, arrodonit a 2 decimals).

L'ID del puzzle és el nom del fitxer sense extensió. Si el fitxer ve de `download.py`, el nom ja és el hash SHA-256.

Comandes:

```bash
# Enviar vot (requereix token UPC)
pixi run python src/rate.py src/puzzles/<id>.json --token <TOKEN>

# Provar sense enviar
pixi run python src/rate.py src/puzzles/<id>.json --token <TOKEN> --dry-run
```

## Funcionalitats útils de graph-tool per avaluar puzzles

`graph-tool` és la llibreria externa que fem servir per treballar amb grafs. La idea per a `eval.py` és reutilitzar aquestes funcionalitats per mesurar propietats del graf d'un puzzle i aprofitar-les per avaluar puzzles o generar-ne de nous de més qualitat.

Selecció inicial de funcionalitats útils:

1. `shortest_distance`
- Calcula distàncies mínimes entre nodes.
- En el projecte pot servir per mesurar la distància entre l'estat inicial i els objectius.
- Un puzzle amb una solució mínima llarga pot ser més difícil o més interessant.

2. `shortest_path`
- Retorna un camí mínim entre dos nodes.
- Ja tenim `solve.py` per obtenir la solució, però aquesta funció també pot ser útil per validar resultats o comparar camins.

3. `label_components`
- Detecta components connexes del graf.
- En el nostre cas, el graf construït des de l'inicial ja és el component connex accessible, però pot ser útil per validar el graf o estudiar-ne variants.

4. `betweenness`
- Calcula centralitat de nodes i arestes.
- Pot ajudar a detectar colls d'ampolla: estats pels quals passen molts camins curts.
- Un puzzle amb colls d'ampolla clars pot tenir estructura més interessant.

5. `pagerank` o altres centralitats
- Mesuren la importància estructural de nodes dins del graf.
- Poden ajudar a veure si el graf està dominat per unes poques configuracions centrals o si és més homogeni.

6. `global_clustering`
- Mesura fins a quin punt els veïns d'un node també estan connectats entre ells.
- Pot servir per distingir grafs amb zones molt denses de grafs molt lineals.

7. `label_largest_component`
- Retorna la component connexa més gran.
- Pot ser útil si més endavant es generen grafs de manera diferent o es comparen puzzles no necessàriament explorats des de l'inicial.

Interpretació per al projecte:

- Longitud de la solució mínima: indica dificultat bàsica.
- Nombre de nodes i arestes: indica mida de l'espai d'estats.
- Colls d'ampolla i centralitats: indiquen si el puzzle obliga a passar per fases concretes.
- Clustering o densitat local: indica si hi ha molta flexibilitat local o estructura més rígida.

Les mesures 1, 3, 4 i 6 estan integrades a la heurística v2 de `eval.py`; la 4 (betweenness de vèrtexs) és ara part central de la puntuació.

## Investigació 2: visualitzar grafs i definir propietats d'avaluació

Anàlisi dels grafs existents per validar i afinar la heurística v2 de `eval.py`.

Objectiu:

- Comparar estructures de grafs de puzzles diferents.
- Relacionar estructura del graf amb dificultat percebuda.
- Seleccionar un conjunt curt de mètriques útils per puntuar puzzles.

Metodologia aplicada:

1. Visualitzar cada graf amb `3D_view.py`.
2. Mirar la ruta de solució ressaltada en groc quan hi ha `.sol.json`.
3. Comparar mida del graf (nodes/arestes), longitud de solució i forma global.
4. Identificar si el graf té colls d'ampolla, zones denses o estructura molt lineal.

Comandes utilitzades:

```bash
# Visualització simple del graf
pixi run python src/3D_view.py puzzles/2swap.graphml
pixi run python src/3D_view.py puzzles/simplicity.graphml
pixi run python src/3D_view.py puzzles/sample3.graphml

# Visualització del graf amb camí de solució
pixi run python src/3D_view.py puzzles/2swap.graphml puzzles/2swap.sol.json
pixi run python src/3D_view.py puzzles/simplicity.graphml puzzles/simplicity.sol.json
pixi run python src/3D_view.py puzzles/sample3.graphml puzzles/sample3.sol.json
```

Observacions inicials:

- La mida del graf varia molt entre puzzles (per exemple, `sample1` és molt més gran que `sample3`).
- Longituds de solució observades en fitxers existents:
  - `2swap`: 17 moviments.
  - `sample3`: 29 moviments.
  - `simplicity`: 31 moviments.
- Els puzzles amb camí mínim més llarg tendeixen a requerir més reorganització intermèdia.
- En el nostre flux (graf construït des de l'estat inicial), el nombre de components connexos és habitualment 1; per tant, aquesta mètrica és sobretot de validació i no de dificultat.

Propietats implementades a `eval.py` (v2):

1. `min_solution_len` + sòl mínim de 10 moviments.
2. `nodes` (amb sòl de 50 nodes) i `path_density`.
3. `avg_degree` en banda mitjana (~2.8).
4. `dead_end_ratio` (penalització −15 %).
5. `max_vertex_betweenness` (pes +15 %).
6. `global_clustering` (pes +5 %).
7. `solvable` → 0 estrelles si no es pot resoldre.

Decisió pràctica:

- Components connexos: comprovació estructural (no puntua directament).
- Calibrar pesos comparant l'ordre de `stars` amb puzzles provats manualment (`play.py`, `3D_view.py`).

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

## Estat del projecte i pendents

| Eina | Estat |
|------|--------|
| `download.py`, `graph.py`, `solve.py`, `eval.py`, `rate.py` | Implementats |
| `generate.py`, `upload.py` | Pendents |
| `rate_all.py` | Opcional (revalorar tots els puzzles del repo) |

Flux recomanat per valorar puzzles d'altres grups:

1. `download.py --out src/puzzles`
2. `eval.py ... --json` (comparar puntuacions)
3. `rate.py ... --token` (enviar vots al repositori)

**Entrega**: ZIP sense la carpeta `.pixi` (~1.3 GB).

## Estat del projecte i pendents

| Eina | Estat |
|------|--------|
| `download.py`, `graph.py`, `solve.py`, `eval.py`, `rate.py` | Implementats |
| `generate.py`, `upload.py` | Pendents |
| `rate_all.py` | Opcional (revalorar tots els puzzles del repo) |

Flux recomanat per valorar puzzles d'altres grups:

1. `download.py --out src/puzzles`
2. `eval.py ... --json` (comparar puntuacions)
3. `rate.py ... --token` (enviar votos al repositori)

**Entrega**: ZIP sense la carpeta `.pixi` (~1.3 GB).

