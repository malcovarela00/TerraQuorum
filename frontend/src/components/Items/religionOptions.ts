export const RELIGION_SEPARATOR = " > "

export const RELIGION_OPTIONS: Array<{
  category: string
  subcategories: string[]
}> = [
  {
    category: "Cristianismo",
    subcategories: [
      "Catolicismo",
      "Ortodoxia oriental",
      "Ortodoxia oriental antigua",
      "Protestantismo - Anglicanos",
      "Protestantismo - Luteranos",
      "Protestantismo - Bautistas",
      "Protestantismo - Metodistas",
      "Protestantismo - Pentecostales",
      "Protestantismo - Reformados/Anabaptistas",
    ],
  },
  {
    category: "Islam",
    subcategories: [
      "Sunismo",
      "Chiismo",
      "Ibadismo",
      "Ahmadia",
      "Sufismo (corriente transversal)",
    ],
  },
  {
    category: "Judaismo",
    subcategories: [
      "Ortodoxo",
      "Conservador",
      "Reformista",
      "Reconstruccionista",
      "Ashkenazi",
      "Sefardi",
    ],
  },
  {
    category: "Hinduismo",
    subcategories: ["Vaishnavismo", "Shaivismo", "Shaktismo", "Smartismo"],
  },
  {
    category: "Budismo",
    subcategories: ["Theravada", "Mahayana", "Vajrayana"],
  },
  {
    category: "Sin afiliacion religiosa",
    subcategories: [
      "Ateo",
      "Agnostico",
      "Secular / no religioso",
      "Esceptico religioso",
    ],
  },
  {
    category: "Otras religiones",
    subcategories: [
      "Sijismo",
      "Religiones populares o tradicionales",
      "Bahaismo",
      "Taoismo",
      "Sintoismo",
      "Jainismo",
      "Otra / no especificada",
    ],
  },
]

export type ReligionCategory = (typeof RELIGION_OPTIONS)[number]["category"]

export function getSubcategories(category: string): string[] {
  const option = RELIGION_OPTIONS.find((entry) => entry.category === category)
  return option ? [...option.subcategories] : []
}

export function composeReligion(category: string, subcategory: string): string {
  return `${category}${RELIGION_SEPARATOR}${subcategory}`
}

export function parseReligion(religion: string | null | undefined): {
  category: string
  subcategory: string
  isKnownCombination: boolean
} {
  const safeReligion = religion ?? ""
  const [category = "", subcategory = ""] = safeReligion
    .split(RELIGION_SEPARATOR)
    .map((part) => part.trim())

  const matchedCategory = RELIGION_OPTIONS.find(
    (entry) => entry.category === category,
  )
  const isKnownCombination = Boolean(
    matchedCategory?.subcategories.includes(subcategory),
  )

  return {
    category,
    subcategory,
    isKnownCombination,
  }
}

export function splitReligionForDisplay(religion: string | null | undefined): {
  category: string
  subcategory: string
} {
  const safeReligion = religion ?? ""
  const parsed = parseReligion(safeReligion)
  if (parsed.category && parsed.subcategory) {
    return { category: parsed.category, subcategory: parsed.subcategory }
  }
  return {
    category: "Otras religiones",
    subcategory: safeReligion || "No especificada",
  }
}
