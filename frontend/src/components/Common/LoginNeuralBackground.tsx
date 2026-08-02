import { useEffect, useRef } from "react"
import * as THREE from "three"

const NODE_COUNT = 280
const SPHERE_RADIUS = 11
const LINK_DISTANCE = 2.8
const MAX_LINKS_PER_NODE = 4

type NodeData = {
  position: THREE.Vector3
  color: THREE.Color
}

function createGlobeNodes(): NodeData[] {
  const nodes: NodeData[] = []
  const goldenAngle = Math.PI * (3 - Math.sqrt(5))

  for (let index = 0; index < NODE_COUNT; index++) {
    const y = 1 - (index / (NODE_COUNT - 1)) * 2
    const radius = Math.sqrt(1 - y * y)
    const theta = goldenAngle * index

    const position = new THREE.Vector3(
      Math.cos(theta) * radius * SPHERE_RADIUS,
      y * SPHERE_RADIUS,
      Math.sin(theta) * radius * SPHERE_RADIUS,
    )

    const t = (y + 1) * 0.5
    const color = new THREE.Color().setHSL(0.62 + t * 0.08, 0.85, 0.56)

    nodes.push({ position, color })
  }

  return nodes
}

export function LoginNeuralBackground() {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const container = containerRef.current
    const canvas = canvasRef.current
    if (!container || !canvas) return

    const scene = new THREE.Scene()
    scene.fog = new THREE.FogExp2(0x03030a, 0.03)

    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x050508, 1)

    const camera = new THREE.PerspectiveCamera(52, 1, 0.1, 200)
    camera.position.set(0, 0, 31)

    const networkGroup = new THREE.Group()
    scene.add(networkGroup)

    const ambientLight = new THREE.AmbientLight(0x9aa6ff, 0.7)
    const pointLight = new THREE.PointLight(0x8ca5ff, 2.2, 140)
    pointLight.position.set(14, 12, 18)
    scene.add(ambientLight, pointLight)

    const nodes = createGlobeNodes()
    const nodePositionData: number[] = []
    const nodeColorData: number[] = []

    for (const node of nodes) {
      nodePositionData.push(node.position.x, node.position.y, node.position.z)
      nodeColorData.push(node.color.r, node.color.g, node.color.b)
    }

    const nodeGeometry = new THREE.BufferGeometry()
    nodeGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(nodePositionData, 3),
    )
    nodeGeometry.setAttribute(
      "color",
      new THREE.Float32BufferAttribute(nodeColorData, 3),
    )

    const nodeMaterial = new THREE.PointsMaterial({
      size: 0.26,
      sizeAttenuation: true,
      vertexColors: true,
      transparent: true,
      opacity: 0.95,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })

    const points = new THREE.Points(nodeGeometry, nodeMaterial)
    networkGroup.add(points)

    const connectionPositions: number[] = []
    const connectionColors: number[] = []
    const linkedPairs = new Set<string>()

    for (let i = 0; i < nodes.length; i++) {
      const source = nodes[i]
      const nearest: Array<{ index: number; distance: number }> = []

      for (let j = 0; j < nodes.length; j++) {
        if (i === j) continue
        const distance = source.position.distanceTo(nodes[j].position)
        if (distance > LINK_DISTANCE) continue
        nearest.push({ index: j, distance })
      }

      nearest.sort((a, b) => a.distance - b.distance)

      for (const candidate of nearest.slice(0, MAX_LINKS_PER_NODE)) {
        const key = [
          Math.min(i, candidate.index),
          Math.max(i, candidate.index),
        ].join("-")
        if (linkedPairs.has(key)) continue
        linkedPairs.add(key)

        const target = nodes[candidate.index]
        connectionPositions.push(
          source.position.x,
          source.position.y,
          source.position.z,
          target.position.x,
          target.position.y,
          target.position.z,
        )

        const gradientColor = source.color.clone().lerp(target.color, 0.5)
        connectionColors.push(
          gradientColor.r,
          gradientColor.g,
          gradientColor.b,
          gradientColor.r,
          gradientColor.g,
          gradientColor.b,
        )
      }
    }

    const connectionGeometry = new THREE.BufferGeometry()
    connectionGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(connectionPositions, 3),
    )
    connectionGeometry.setAttribute(
      "color",
      new THREE.Float32BufferAttribute(connectionColors, 3),
    )

    const connectionMaterial = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.33,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })

    const lines = new THREE.LineSegments(connectionGeometry, connectionMaterial)
    networkGroup.add(lines)

    const haloGeometry = new THREE.SphereGeometry(SPHERE_RADIUS + 0.45, 32, 32)
    const haloMaterial = new THREE.MeshBasicMaterial({
      color: 0x7b8cff,
      wireframe: true,
      transparent: true,
      opacity: 0.06,
    })
    const halo = new THREE.Mesh(haloGeometry, haloMaterial)
    networkGroup.add(halo)

    const clock = new THREE.Clock()
    let frame = 0

    const resize = () => {
      const { clientWidth, clientHeight } = container
      if (clientWidth === 0 || clientHeight === 0) return
      camera.aspect = clientWidth / clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(clientWidth, clientHeight, false)
    }

    resize()
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(container)

    const animate = () => {
      frame = window.requestAnimationFrame(animate)
      const elapsed = clock.getElapsedTime()

      networkGroup.rotation.y = elapsed * 0.22
      networkGroup.rotation.x = Math.sin(elapsed * 0.18) * 0.09

      const pulse = 1 + Math.sin(elapsed * 1.2) * 0.03
      points.scale.setScalar(pulse)
      connectionMaterial.opacity = 0.26 + Math.sin(elapsed * 0.8) * 0.08
      halo.rotation.y = -elapsed * 0.08
      halo.rotation.z = elapsed * 0.06

      renderer.render(scene, camera)
    }

    animate()

    return () => {
      window.cancelAnimationFrame(frame)
      resizeObserver.disconnect()
      nodeGeometry.dispose()
      connectionGeometry.dispose()
      haloGeometry.dispose()
      nodeMaterial.dispose()
      connectionMaterial.dispose()
      haloMaterial.dispose()
      renderer.dispose()
      scene.clear()
    }
  }, [])

  return (
    <div ref={containerRef} className="absolute inset-0">
      <canvas ref={canvasRef} className="h-full w-full" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(102,126,234,0.22),transparent_48%),radial-gradient(circle_at_80%_15%,rgba(118,75,162,0.2),transparent_50%),linear-gradient(180deg,rgba(5,5,8,0.12),rgba(5,5,8,0.78))]" />
    </div>
  )
}
