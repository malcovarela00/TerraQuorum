import { useQuery } from "@tanstack/react-query"
import { Globe2, Map as MapIcon, Minus, Plus, RotateCcw } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  ComposableMap,
  Geographies,
  Geography,
  Graticule,
  Sphere,
  ZoomableGroup,
  type ZoomableGroupProps,
} from "react-simple-maps"

import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useSidebar } from "@/components/ui/sidebar"
import { useI18n } from "@/i18n"
import { cn } from "@/lib/utils"

const WORLD_TOPOLOGY_URL =
  "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"

const MAP_BASE = { width: 1000, height: 520 } as const

type MapPalette = {
  sphereFill: string
  sphereStroke: string
  countryFill: string
  countryStroke: string
  countryHoverStroke: string
  graticule: string
  noData: string
  oceanCenter: string
  oceanEdge: string
  glow: string
}

const MAP_PALETTES: Record<"light" | "dark", MapPalette> = {
  light: {
    sphereFill: "#CFEAF5",
    sphereStroke: "#8BBED0",
    countryFill: "#A9C77B",
    countryStroke: "rgba(70, 91, 74, 0.24)",
    countryHoverStroke: "#4F7B57",
    graticule: "rgba(57, 111, 135, 0.14)",
    noData: "#D8D3BE",
    oceanCenter: "#DDF4FB",
    oceanEdge: "#91CFE4",
    glow: "rgba(88, 157, 179, 0.22)",
  },
  dark: {
    sphereFill: "#101728",
    sphereStroke: "#273450",
    countryFill: "#28324b",
    countryStroke: "rgba(148, 163, 184, 0.22)",
    countryHoverStroke: "#93c5fd",
    graticule: "rgba(148, 163, 184, 0.12)",
    noData: "#1d2639",
    oceanCenter: "#1c2b4d",
    oceanEdge: "#0a101f",
    glow: "rgba(96, 165, 250, 0.22)",
  },
}

/** Tonos naturales para diferenciar países sin datos en modo claro */
const LIGHT_PATCHWORK_COLORS = [
  "#96BE6B",
  "#C7B46B",
  "#7FB49B",
  "#D7A66B",
] as const

/** Escalas continuas por tema para datos numéricos */
const COLOR_SCALES: Record<"light" | "dark", readonly string[]> = {
  light: [
    "#E5E1C8",
    "#D5D69B",
    "#BBCB78",
    "#98BD67",
    "#71AA60",
    "#4E965C",
    "#2F805A",
    "#1B6A5E",
    "#0F5260",
  ],
  dark: [
    "#1e2f5e",
    "#1e40af",
    "#1d4ed8",
    "#2563eb",
    "#3b82f6",
    "#60a5fa",
    "#93c5fd",
    "#bfdbfe",
    "#e0edff",
  ],
}

const CATEGORY_COLORS: Record<"light" | "dark", readonly string[]> = {
  light: [
    "#4F8F5B",
    "#C08A3E",
    "#2F7C78",
    "#B76E55",
    "#7C8D3B",
    "#8A6F9E",
    "#D3A846",
    "#5C9AA3",
    "#A6634B",
    "#6C9B6F",
  ],
  dark: [
    "#60a5fa",
    "#4ade80",
    "#f87171",
    "#c084fc",
    "#fb923c",
    "#22d3ee",
    "#818cf8",
    "#fb7185",
    "#a3e635",
    "#a78bfa",
  ],
}

const MIN_ZOOM = 1
const MAX_ZOOM = 6
const DEFAULT_POSITION = {
  coordinates: [0, 12] as [number, number],
  zoom: 1.15,
}

const GLOBE_MIN_SCALE = 170
const GLOBE_MAX_SCALE = 620
const GLOBE_DEFAULT_SCALE = 238
/** Rotación inicial del globo: centra el Atlántico / Europa-África */
const GLOBE_DEFAULT_ROTATION: [number, number] = [-12, -22]
/** Velocidad de auto-rotación en grados por milisegundo (~3°/s) */
const GLOBE_AUTOROTATE_SPEED = 0.003

type MapMode = "flat" | "globe"

type CountryMapPoint = {
  country_name: string
  iso_numeric: string | null
  custom_data: Record<string, MapValue>
}

type MapValue = number | string | null

type MapDataResponse = {
  data: CountryMapPoint[]
  available_keys: string[]
}

const API_BASE = import.meta.env.VITE_API_URL ?? ""

async function fetchMapData(): Promise<MapDataResponse> {
  const token = localStorage.getItem("access_token") ?? ""
  const res = await fetch(`${API_BASE}/api/v1/countries/map-data`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error("Error al cargar datos del mapa")
  return res.json()
}

function getScaleColor(
  value: number,
  min: number,
  max: number,
  scale: readonly string[],
): string {
  if (max === min) return scale[4]
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)))
  const idx = Math.min(Math.floor(t * scale.length), scale.length - 1)
  return scale[idx]
}

function formatDataKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatNumber(n: number, locale: string): string {
  if (Number.isInteger(n) && Math.abs(n) >= 1000) {
    return n.toLocaleString(locale)
  }
  return n.toLocaleString(locale, { maximumFractionDigits: 2 })
}

function formatMapValue(
  value: MapValue | undefined,
  locale: string,
  noDataLabel: string,
): string {
  if (typeof value === "number") return formatNumber(value, locale)
  if (typeof value === "string" && value.trim()) return value
  return noDataLabel
}

type TooltipInfo = {
  x: number
  y: number
  name: string
  value: MapValue | undefined
  dataKey: string
}

type TopoGeometry = {
  type: "Polygon" | "MultiPolygon"
  arcs: number[][] | number[][][]
  id: string | number
}

function collectTopoArcs(geometry: TopoGeometry): number[] {
  if (geometry.type === "Polygon") {
    return (geometry.arcs as number[][]).flat()
  }
  return (geometry.arcs as number[][][]).flat(2)
}

function buildTopoNeighbors(geometries: TopoGeometry[]): number[][] {
  const indexesByArc = new Map<number, number[]>()
  const neighbors = geometries.map(() => [] as number[])

  for (const [i, geometry] of geometries.entries()) {
    for (const arcRef of collectTopoArcs(geometry)) {
      const arcIndex = arcRef < 0 ? ~arcRef : arcRef
      const list = indexesByArc.get(arcIndex) ?? []
      list.push(i)
      indexesByArc.set(arcIndex, list)
    }
  }

  for (const [i, geometry] of geometries.entries()) {
    const seen = new Set<number>()
    for (const arcRef of collectTopoArcs(geometry)) {
      const arcIndex = arcRef < 0 ? ~arcRef : arcRef
      for (const j of indexesByArc.get(arcIndex) ?? []) {
        if (j !== i && !seen.has(j)) {
          seen.add(j)
          neighbors[i].push(j)
        }
      }
    }
  }

  return neighbors
}

function assignPatchworkColors(neighbors: number[][]): number[] {
  const colors = new Array<number>(neighbors.length).fill(0)
  for (let i = 0; i < neighbors.length; i++) {
    const used = new Set<number>()
    for (const j of neighbors[i]) {
      used.add(colors[j])
    }
    let picked = 0
    for (let c = 0; c < LIGHT_PATCHWORK_COLORS.length; c++) {
      if (!used.has(c)) {
        picked = c
        break
      }
    }
    colors[i] = picked
  }
  return colors
}

export default function WorldMapCard() {
  const { isMobile, state } = useSidebar()
  const { locale, t } = useI18n()
  const { resolvedTheme } = useTheme()
  const mapColors = MAP_PALETTES[resolvedTheme]
  const countryStrokeWidth = resolvedTheme === "light" ? 0.28 : 0.35
  const sphereStrokeWidth = resolvedTheme === "light" ? 0.5 : 0.65
  const colorScale = COLOR_SCALES[resolvedTheme]
  const categoryColors = CATEGORY_COLORS[resolvedTheme]
  const numberLocale = locale === "es" ? "es-ES" : "en-US"
  const isSidebarCollapsed = !isMobile && state === "collapsed"
  const [patchworkByIso, setPatchworkByIso] = useState<Map<string, string>>(
    () => new Map(),
  )
  const [mode, setMode] = useState<MapMode>("flat")
  const [position, setPosition] = useState(DEFAULT_POSITION)
  const [rotation, setRotation] = useState<[number, number]>(
    GLOBE_DEFAULT_ROTATION,
  )
  const [globeScale, setGlobeScale] = useState(GLOBE_DEFAULT_SCALE)
  const [isDragging, setIsDragging] = useState(false)
  const [selectedKey, setSelectedKey] = useState<string>("")
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null)
  const dragRef = useRef<{ x: number; y: number } | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(WORLD_TOPOLOGY_URL)
      .then((res) => res.json())
      .then((topology) => {
        const geometries = topology.objects.countries
          .geometries as TopoGeometry[]
        const neighborGraph = buildTopoNeighbors(geometries)
        const colorIndexes = assignPatchworkColors(neighborGraph)
        const byIso = new Map<string, string>()
        for (const [i, geometry] of geometries.entries()) {
          byIso.set(
            String(geometry.id),
            LIGHT_PATCHWORK_COLORS[colorIndexes[i]],
          )
        }
        if (!cancelled) setPatchworkByIso(byIso)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const { data: mapData } = useQuery({
    queryKey: ["countries-map-data"],
    queryFn: fetchMapData,
    refetchInterval: 30_000,
    staleTime: 10_000,
  })

  const availableKeys = mapData?.available_keys ?? []

  const activeKey = selectedKey || availableKeys[0] || ""

  const isoToData = useMemo(() => {
    const map = new Map<string, { name: string; value: MapValue }>()
    if (!mapData?.data || !activeKey) return map
    for (const point of mapData.data) {
      if (!point.iso_numeric) continue
      const val = point.custom_data[activeKey]
      map.set(point.iso_numeric, {
        name: point.country_name,
        value: typeof val === "number" || typeof val === "string" ? val : null,
      })
    }
    return map
  }, [mapData, activeKey])

  const activeValues = useMemo(
    () =>
      Array.from(isoToData.values())
        .map((entry) => entry.value)
        .filter((value): value is number | string => value != null),
    [isoToData],
  )

  const isNumericData =
    activeValues.length > 0 &&
    activeValues.every((value) => typeof value === "number")

  const { minVal, maxVal } = useMemo(() => {
    let min = Infinity
    let max = -Infinity
    for (const entry of isoToData.values()) {
      if (typeof entry.value === "number") {
        if (entry.value < min) min = entry.value
        if (entry.value > max) max = entry.value
      }
    }
    return {
      minVal: min === Infinity ? 0 : min,
      maxVal: max === -Infinity ? 0 : max,
    }
  }, [isoToData])

  const categories = useMemo(() => {
    const unique = new Set<string>()
    for (const value of activeValues) {
      if (typeof value === "string" && value.trim()) unique.add(value.trim())
    }
    return Array.from(unique).sort((a, b) => a.localeCompare(b, locale))
  }, [activeValues, locale])

  const hasData =
    availableKeys.length > 0 && activeKey && activeValues.length > 0

  const isGlobe = mode === "globe"

  /* ------------------------------ Controles ------------------------------ */

  const handleMoveEnd: ZoomableGroupProps["onMoveEnd"] = (nextPosition) => {
    setPosition({
      coordinates: nextPosition.coordinates as [number, number],
      zoom: nextPosition.zoom,
    })
  }

  const handleZoomIn = () => {
    if (isGlobe) {
      setGlobeScale((current) => Math.min(current * 1.25, GLOBE_MAX_SCALE))
      return
    }
    setPosition((current) => ({
      ...current,
      zoom: Math.min(current.zoom * 1.25, MAX_ZOOM),
    }))
  }

  const handleZoomOut = () => {
    if (isGlobe) {
      setGlobeScale((current) => Math.max(current / 1.25, GLOBE_MIN_SCALE))
      return
    }
    setPosition((current) => ({
      ...current,
      zoom: Math.max(current.zoom / 1.25, MIN_ZOOM),
    }))
  }

  const handleReset = () => {
    if (isGlobe) {
      setRotation(GLOBE_DEFAULT_ROTATION)
      setGlobeScale(GLOBE_DEFAULT_SCALE)
      return
    }
    setPosition(DEFAULT_POSITION)
  }

  const handleGlobeWheel = useCallback(
    (evt: React.WheelEvent<HTMLDivElement>) => {
      if (!isGlobe) return

      evt.preventDefault()
      setTooltip(null)

      const zoomFactor = Math.exp(-evt.deltaY * 0.0012)
      setGlobeScale((current) =>
        Math.max(
          GLOBE_MIN_SCALE,
          Math.min(current * zoomFactor, GLOBE_MAX_SCALE),
        ),
      )
    },
    [isGlobe],
  )

  /* --------------------- Rotación del globo (drag + auto) --------------------- */

  const handlePointerDown = useCallback(
    (evt: React.PointerEvent<HTMLDivElement>) => {
      if (!isGlobe) return
      dragRef.current = { x: evt.clientX, y: evt.clientY }
      setIsDragging(true)
      setTooltip(null)
      evt.currentTarget.setPointerCapture(evt.pointerId)
    },
    [isGlobe],
  )

  const handlePointerMove = useCallback(
    (evt: React.PointerEvent<HTMLDivElement>) => {
      if (!isGlobe || !dragRef.current) return
      const dx = evt.clientX - dragRef.current.x
      const dy = evt.clientY - dragRef.current.y
      dragRef.current = { x: evt.clientX, y: evt.clientY }
      const sensitivity = 75 / globeScale
      setRotation(([lambda, phi]) => [
        lambda + dx * sensitivity,
        Math.max(-85, Math.min(85, phi - dy * sensitivity)),
      ])
    },
    [isGlobe, globeScale],
  )

  const handlePointerUp = useCallback(() => {
    dragRef.current = null
    setIsDragging(false)
  }, [])

  const isTooltipVisible = tooltip !== null

  useEffect(() => {
    if (!isGlobe || isDragging || isTooltipVisible) return
    let raf = 0
    let prev = performance.now()
    const tick = (now: number) => {
      const dt = now - prev
      prev = now
      setRotation(([lambda, phi]) => [
        lambda + dt * GLOBE_AUTOROTATE_SPEED,
        phi,
      ])
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [isGlobe, isDragging, isTooltipVisible])

  /* ------------------------------- Colores ------------------------------- */

  const getCountryFill = useCallback(
    (geoId: string): string => {
      if (resolvedTheme === "light") {
        if (hasData) {
          const entry = isoToData.get(geoId)
          if (!entry || entry.value == null) return mapColors.noData
          if (typeof entry.value === "number") {
            return getScaleColor(entry.value, minVal, maxVal, colorScale)
          }
          const categoryIndex = categories.indexOf(entry.value.trim())
          return categoryColors[
            Math.max(0, categoryIndex) % categoryColors.length
          ]
        }
        return patchworkByIso.get(geoId) ?? mapColors.countryFill
      }

      if (!hasData) return mapColors.countryFill
      const entry = isoToData.get(geoId)
      if (!entry || entry.value == null) return mapColors.noData
      if (typeof entry.value === "number") {
        return getScaleColor(entry.value, minVal, maxVal, colorScale)
      }
      const categoryIndex = categories.indexOf(entry.value.trim())
      return categoryColors[Math.max(0, categoryIndex) % categoryColors.length]
    },
    [
      resolvedTheme,
      hasData,
      isoToData,
      minVal,
      maxVal,
      categories,
      mapColors,
      colorScale,
      categoryColors,
      patchworkByIso,
    ],
  )

  const handleMouseEnter = useCallback(
    (
      geo: { id: string; properties: { name?: string } },
      evt: React.MouseEvent,
    ) => {
      if (dragRef.current) return
      const geoId = String(geo.id)
      const entry = isoToData.get(geoId)
      const name = entry?.name ?? geo.properties.name ?? t("map.unknownCountry")
      const value = entry?.value
      setTooltip({
        x: evt.clientX,
        y: evt.clientY,
        name,
        value: value ?? (hasData ? undefined : null),
        dataKey: activeKey,
      })
    },
    [isoToData, activeKey, hasData, t],
  )

  const handleMouseMove = useCallback((evt: React.MouseEvent) => {
    setTooltip((prev) =>
      prev ? { ...prev, x: evt.clientX, y: evt.clientY } : null,
    )
  }, [])

  const handleMouseLeave = useCallback(() => {
    setTooltip(null)
  }, [])

  /* ------------------------------- Geografías ------------------------------- */

  const renderGeographies = (
    <Geographies geography={WORLD_TOPOLOGY_URL}>
      {({ geographies }) =>
        geographies.map((geography) => {
          const geoId = String(geography.id)
          const fill = getCountryFill(geoId)
          return (
            <Geography
              key={geography.rsmKey}
              geography={geography}
              onMouseEnter={(evt) =>
                handleMouseEnter(
                  { id: geoId, properties: geography.properties },
                  evt,
                )
              }
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
              style={{
                default: {
                  fill,
                  stroke: mapColors.countryStroke,
                  strokeWidth: countryStrokeWidth,
                  outline: "none",
                  transition:
                    "fill 0.15s ease, filter 0.15s ease, stroke 0.15s ease",
                },
                hover: {
                  fill: resolvedTheme === "light" ? "#FFF8E8" : fill,
                  stroke: mapColors.countryHoverStroke,
                  strokeWidth: countryStrokeWidth + 0.35,
                  outline: "none",
                  filter:
                    resolvedTheme === "light"
                      ? "brightness(1.04) drop-shadow(0 0 5px rgba(79, 123, 87, 0.22))"
                      : "brightness(1.08) drop-shadow(0 0 3px rgba(96, 165, 250, 0.35))",
                },
                pressed: {
                  fill: resolvedTheme === "light" ? "#FFF8E8" : fill,
                  stroke: mapColors.countryHoverStroke,
                  strokeWidth: countryStrokeWidth + 0.35,
                  outline: "none",
                },
              }}
            />
          )
        })
      }
    </Geographies>
  )

  const mapDefs = (
    <defs>
      <radialGradient id="map-ocean-gradient" cx="38%" cy="32%" r="75%">
        <stop offset="0%" stopColor={mapColors.oceanCenter} />
        <stop offset="100%" stopColor={mapColors.oceanEdge} />
      </radialGradient>
      <radialGradient id="map-globe-shine" cx="34%" cy="26%" r="60%">
        <stop
          offset="0%"
          stopColor="#5DA2FF"
          stopOpacity={resolvedTheme === "dark" ? 0.1 : 0.08}
        />
        <stop offset="55%" stopColor="#ffffff" stopOpacity={0} />
        <stop offset="100%" stopColor="#ffffff" stopOpacity={0} />
      </radialGradient>
    </defs>
  )

  return (
    <Card
      className={cn(
        "border-border/60 bg-gradient-to-b from-card via-background to-muted/15",
        isSidebarCollapsed ? "xl:min-h-[780px]" : "xl:min-h-[700px]",
      )}
    >
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="icon-chip hidden sm:flex">
              <Globe2 className="size-5" />
            </span>
            <div className="min-w-0">
              <CardTitle className="text-xl font-semibold">
                {t("map.title")}
              </CardTitle>
              <p className="text-muted-foreground truncate text-base">
                {hasData
                  ? t("map.showing", { label: formatDataKey(activeKey) })
                  : t("map.viewGlobal")}
              </p>
            </div>
          </div>
          {availableKeys.length > 0 && (
            <Select value={activeKey} onValueChange={setSelectedKey}>
              <SelectTrigger className="w-52">
                <SelectValue placeholder={t("map.selectData")} />
              </SelectTrigger>
              <SelectContent>
                {availableKeys.map((key) => (
                  <SelectItem key={key} value={key}>
                    {formatDataKey(key)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-1">
        <div
          className={cn(
            "map-surface relative flex min-h-0 flex-col overflow-hidden",
            isSidebarCollapsed
              ? "min-h-[500px] xl:min-h-[640px]"
              : "min-h-[480px] xl:min-h-[580px]",
          )}
        >
          {/* Selector de modo 2D / 3D */}
          <div className="absolute top-4 left-4 z-10 flex items-center gap-0.5 rounded-full border border-border/50 bg-background/85 p-1 shadow-md shadow-slate-900/8 ring-1 ring-black/5 backdrop-blur-md dark:bg-background/75 dark:ring-white/10">
            <Button
              type="button"
              variant={isGlobe ? "ghost" : "default"}
              size="sm"
              className="h-8 gap-1.5 rounded-full px-3 text-xs font-medium"
              onClick={() => {
                setMode("flat")
                setTooltip(null)
              }}
              aria-pressed={!isGlobe}
              aria-label={t("map.mode2d")}
            >
              <MapIcon className="size-3.5" />
              <span className="hidden sm:inline">{t("map.mode2d")}</span>
            </Button>
            <Button
              type="button"
              variant={isGlobe ? "default" : "ghost"}
              size="sm"
              className="h-8 gap-1.5 rounded-full px-3 text-xs font-medium"
              onClick={() => {
                setMode("globe")
                setTooltip(null)
              }}
              aria-pressed={isGlobe}
              aria-label={t("map.mode3d")}
            >
              <Globe2 className="size-3.5" />
              <span className="hidden sm:inline">{t("map.mode3d")}</span>
            </Button>
          </div>

          {/* Zoom controls */}
          <div className="absolute top-4 right-4 z-10 flex items-center gap-0.5 rounded-full border border-border/50 bg-background/85 px-1 py-1 shadow-md shadow-slate-900/8 ring-1 ring-black/5 backdrop-blur-md dark:bg-background/75 dark:ring-white/10">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-8 rounded-full"
              onClick={handleZoomOut}
              aria-label={t("map.zoomOut")}
            >
              <Minus className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-8 rounded-full"
              onClick={handleZoomIn}
              aria-label={t("map.zoomIn")}
            >
              <Plus className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-8 rounded-full"
              onClick={handleReset}
              aria-label={t("map.zoomReset")}
            >
              <RotateCcw className="size-4" />
            </Button>
          </div>

          {/* Legend */}
          {hasData && (
            <div className="absolute bottom-4 left-4 z-10 rounded-xl border border-border/50 bg-background/90 px-3 py-2.5 shadow-md shadow-slate-900/8 ring-1 ring-black/5 backdrop-blur-md dark:bg-background/80 dark:ring-white/10">
              <p className="mb-1.5 text-xs font-medium tracking-tight text-foreground/80">
                {formatDataKey(activeKey)}
              </p>
              {isNumericData ? (
                <div className="flex items-center gap-2">
                  <span className="tabular-nums text-[10px] text-muted-foreground">
                    {formatNumber(minVal, numberLocale)}
                  </span>
                  <div
                    className="h-2.5 w-32 rounded-full shadow-inner shadow-slate-900/10"
                    style={{
                      background: `linear-gradient(90deg, ${colorScale.join(", ")})`,
                    }}
                  />
                  <span className="tabular-nums text-[10px] text-muted-foreground">
                    {formatNumber(maxVal, numberLocale)}
                  </span>
                </div>
              ) : (
                <div className="grid max-w-56 gap-1.5">
                  {categories.slice(0, 8).map((category, index) => (
                    <div key={category} className="flex items-center gap-2">
                      <div
                        className="size-2.5 rounded-sm ring-1 ring-border/40"
                        style={{
                          backgroundColor:
                            categoryColors[index % categoryColors.length],
                        }}
                      />
                      <span className="truncate text-[10px] text-muted-foreground">
                        {category}
                      </span>
                    </div>
                  ))}
                  {categories.length > 8 && (
                    <span className="text-[10px] text-muted-foreground">
                      {t("map.moreCategories", {
                        count: categories.length - 8,
                      })}
                    </span>
                  )}
                </div>
              )}
              <div className="mt-2 flex items-center gap-2">
                <div
                  className="size-2.5 rounded-sm ring-1 ring-border/40"
                  style={{ backgroundColor: mapColors.noData }}
                />
                <span className="text-[10px] text-muted-foreground">
                  {t("map.noData")}
                </span>
              </div>
            </div>
          )}

          <div
            className={cn(
              "flex min-h-0 flex-1 items-center justify-center px-1 py-3 sm:px-2",
              isGlobe && (isDragging ? "cursor-grabbing" : "cursor-grab"),
            )}
            style={isGlobe ? { touchAction: "none" } : undefined}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            onWheel={handleGlobeWheel}
          >
            {isGlobe ? (
              <ComposableMap
                projection="geoOrthographic"
                projectionConfig={{
                  rotate: [rotation[0], rotation[1], 0],
                  scale: globeScale,
                }}
                width={MAP_BASE.width}
                height={MAP_BASE.height}
                className="block max-h-[min(58vh,620px)] w-full max-w-full select-none"
                style={{
                  width: "100%",
                  height: "auto",
                  filter: `drop-shadow(0 0 42px ${mapColors.glow})`,
                }}
              >
                {mapDefs}
                <Sphere
                  id="world-sphere"
                  fill="url(#map-ocean-gradient)"
                  stroke={mapColors.sphereStroke}
                  strokeWidth={sphereStrokeWidth}
                />
                <Graticule stroke={mapColors.graticule} strokeWidth={0.4} />
                {renderGeographies}
                {/* Brillo superior para efecto esférico (no bloquea el hover) */}
                <Sphere
                  id="world-sphere-shine"
                  fill="url(#map-globe-shine)"
                  stroke="none"
                  strokeWidth={0}
                  style={{ pointerEvents: "none" }}
                />
              </ComposableMap>
            ) : (
              <ComposableMap
                projection="geoEqualEarth"
                projectionConfig={{ scale: 168 }}
                width={MAP_BASE.width}
                height={MAP_BASE.height}
                className="block max-h-[min(58vh,620px)] w-full max-w-full select-none"
                style={{
                  width: "100%",
                  height: "auto",
                }}
              >
                {mapDefs}
                <ZoomableGroup
                  center={position.coordinates}
                  zoom={position.zoom}
                  minZoom={MIN_ZOOM}
                  maxZoom={MAX_ZOOM}
                  onMoveEnd={handleMoveEnd}
                >
                  <Sphere
                    id="world-sphere"
                    fill="url(#map-ocean-gradient)"
                    stroke={mapColors.sphereStroke}
                    strokeWidth={sphereStrokeWidth}
                  />
                  <Graticule stroke={mapColors.graticule} strokeWidth={0.4} />
                  {renderGeographies}
                </ZoomableGroup>
              </ComposableMap>
            )}
          </div>

          {/* Tooltip */}
          {tooltip && (
            <div
              className="pointer-events-none fixed z-50 max-w-xs rounded-lg border border-border bg-popover px-3 py-2 shadow-lg"
              style={{
                left: tooltip.x + 12,
                top: tooltip.y - 10,
              }}
            >
              <p className="text-sm font-semibold text-popover-foreground">
                {tooltip.name}
              </p>
              {hasData && tooltip.dataKey && (
                <p className="text-xs text-muted-foreground">
                  {formatDataKey(tooltip.dataKey)}:{" "}
                  <span className="font-medium text-popover-foreground">
                    {formatMapValue(
                      tooltip.value,
                      numberLocale,
                      t("map.noData"),
                    )}
                  </span>
                </p>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
