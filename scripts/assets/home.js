/* ==========================================================================
   水浒维基 · 首页星野（唯一例外：全站仅首页与搜索页使用 JS）
   概念出自第七十一回「忠义堂石碣受天文，梁山泊英雄排座次」：
     36 颗天罡星（朱砂）+ 72 颗地煞星（黛蓝），悬于梁山泊夜空，
     倒映于水泊之上。星点闪烁、星野缓转，鼠标/触摸可拨动视角。
   性能约定：粒子全部 GPU 端动画（自定义 shader），CPU 每帧只更新 uniform；
   页面不可见 / 滚出首屏 / prefers-reduced-motion 时停止渲染循环。
   ========================================================================== */

import * as THREE from "./vendor/three.module.min.js";

const canvas = document.getElementById("starfield");
if (canvas) init(canvas);

function init(canvas) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas, antialias: true, alpha: true, powerPreference: "high-performance",
    });
  } catch (e) {
    canvas.remove(); // WebGL 不可用 → 保留 CSS 夜空渐变兜底
    return;
  }

  const DPR = Math.min(window.devicePixelRatio || 1, 2);
  renderer.setPixelRatio(DPR);

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x14100c, 0.0016);

  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 600);
  camera.position.set(0, 10, 92);

  // ---------------------------------------------------------- 星宿（108）
  // 分布：上半球壳层，微微压扁成银河带；天罡星更近更亮（内圈），地煞铺外圈。
  function makeStars(count, radiusMin, radiusMax, size, color, opacity) {
    const pos = new Float32Array(count * 3);
    const phase = new Float32Array(count);
    const scale = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      // 球壳采样，y 偏置向上，形成罩顶星野
      const theta = Math.random() * Math.PI * 2;
      const u = Math.random();
      const yBase = 0.12 + 0.88 * u;                 // 0.12~1 归一化高度
      const r = radiusMin + Math.random() * (radiusMax - radiusMin);
      const ring = Math.sqrt(Math.max(0, 1 - yBase * yBase));
      pos[i * 3]     = Math.cos(theta) * ring * r;
      pos[i * 3 + 1] = yBase * r * 0.72;             // 压扁成天穹
      pos[i * 3 + 2] = Math.sin(theta) * ring * r;
      phase[i] = Math.random() * Math.PI * 2;
      scale[i] = 0.7 + Math.random() * 0.6;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("aPhase", new THREE.BufferAttribute(phase, 1));
    geo.setAttribute("aScale", new THREE.BufferAttribute(scale, 1));

    const mat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTime: { value: 0 },
        uSize: { value: size * DPR },
        uColor: { value: new THREE.Color(color) },
        uOpacity: { value: opacity },
        uReflect: { value: 0 },                       // 1 = 倒影模式
      },
      vertexShader: /* glsl */`
        attribute float aPhase;
        attribute float aScale;
        uniform float uTime, uSize, uReflect;
        varying float vTwinkle;
        void main() {
          vec3 p = position;
          if (uReflect > 0.5) {
            // 水泊倒影：翻到水面下，随波微晃
            p.y = -p.y * 0.55;
            p.x += sin(uTime * 0.9 + position.y * 0.35) * 0.6;
            p.z += cos(uTime * 0.7 + position.x * 0.25) * 0.4;
          }
          float tw = 0.62 + 0.38 * sin(uTime * (0.8 + aScale * 0.7) + aPhase);
          vTwinkle = uReflect > 0.5 ? tw * 0.5 : tw;
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = uSize * aScale * tw * (160.0 / -mv.z);
        }
      `,
      fragmentShader: /* glsl */`
        uniform vec3 uColor;
        uniform float uOpacity;
        varying float vTwinkle;
        void main() {
          // 柔边圆点，中心亮核
          vec2 uv = gl_PointCoord - 0.5;
          float d = length(uv);
          float glow = smoothstep(0.5, 0.0, d);
          float core = smoothstep(0.18, 0.0, d);
          float a = (glow * 0.55 + core * 0.9) * vTwinkle * uOpacity;
          if (a < 0.01) discard;
          gl_FragColor = vec4(uColor, a);
        }
      `,
    });
    return new THREE.Points(geo, mat);
  }

  const CINNABAR = 0xd4573f;   // 暗场中稍提亮，避免朱砂在夜里发闷
  const STARLIGHT = 0xcfd8dc;  // 地煞偏月白，暗合黛蓝的冷调

  const tg36 = makeStars(36, 26, 44, 8.2, CINNABAR, 1.0);        // 天罡 36
  const ds72 = makeStars(72, 40, 66, 5.2, STARLIGHT, 0.9);       // 地煞 72
  const tg36r = makeStars(36, 26, 44, 6.8, CINNABAR, 0.38);      // 倒影
  const ds72r = makeStars(72, 40, 66, 4.2, STARLIGHT, 0.30);
  tg36r.material.uniforms.uReflect.value = 1;
  ds72r.material.uniforms.uReflect.value = 1;

  // 倒影与正星共享几何（同一批星，只是 shader 里翻到水下）
  tg36r.geometry = tg36.geometry;
  ds72r.geometry = ds72.geometry;

  const sky = new THREE.Group();
  sky.add(tg36, ds72, tg36r, ds72r);
  scene.add(sky);

  // ---------------------------------------------------------- 星宿连线（天罡内圈近邻）
  {
    const p = tg36.geometry.attributes.position;
    const verts = [];
    for (let i = 0; i < 36; i++) {
      // 每颗星连向最近的一颗，织成星图
      let best = -1, bestD = Infinity;
      for (let j = 0; j < 36; j++) {
        if (j === i) continue;
        const dx = p.getX(i) - p.getX(j);
        const dy = p.getY(i) - p.getY(j);
        const dz = p.getZ(i) - p.getZ(j);
        const d = dx * dx + dy * dy + dz * dz;
        if (d < bestD) { bestD = d; best = j; }
      }
      verts.push(
        p.getX(i), p.getY(i), p.getZ(i),
        p.getX(best), p.getY(best), p.getZ(best),
      );
    }
    const lgeo = new THREE.BufferGeometry();
    lgeo.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
    const lmat = new THREE.LineBasicMaterial({
      color: 0x8a4a3d, transparent: true, opacity: 0.22,
      blending: THREE.AdditiveBlending, depthWrite: false,
    });
    sky.add(new THREE.LineSegments(lgeo, lmat));
  }

  // ---------------------------------------------------------- 水泊（点阵波面）
  {
    const N = 90, SPAN = 260;
    const pos = new Float32Array(N * N * 3);
    const phase = new Float32Array(N * N);
    let k = 0;
    for (let ix = 0; ix < N; ix++) {
      for (let iz = 0; iz < N; iz++) {
        const x = (ix / (N - 1) - 0.5) * SPAN;
        const z = (iz / (N - 1) - 0.5) * SPAN;
        pos[k * 3] = x;
        pos[k * 3 + 1] = 0;
        pos[k * 3 + 2] = z;
        phase[k] = Math.hypot(x, z) * 0.11;   // 涟漪相位随半径扩散
        k++;
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("aPhase", new THREE.BufferAttribute(phase, 1));
    const mat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: { uTime: { value: 0 }, uDpr: { value: DPR } },
      vertexShader: /* glsl */`
        attribute float aPhase;
        uniform float uTime, uDpr;
        varying float vA;
        void main() {
          vec3 p = position;
          float w = sin(uTime * 1.1 + aPhase) * cos(uTime * 0.6 + p.x * 0.08);
          p.y = w * 0.9;
          // 近岸亮、远处没入夜色
          float dist = length(position.xz);
          vA = (0.5 + 0.5 * w) * smoothstep(130.0, 30.0, dist) * 0.65;
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = 1.6 * uDpr * (120.0 / -mv.z);
        }
      `,
      fragmentShader: /* glsl */`
        varying float vA;
        void main() {
          vec2 uv = gl_PointCoord - 0.5;
          float a = smoothstep(0.5, 0.0, length(uv)) * vA;
          if (a < 0.01) discard;
          gl_FragColor = vec4(0.36, 0.47, 0.55, a);   // 黛蓝波光
        }
      `,
    });
    const water = new THREE.Points(geo, mat);
    water.position.y = -1.2;
    water.name = "water";
    scene.add(water);
  }

  // ---------------------------------------------------------- 交互与循环
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let mx = 0, my = 0;             // 鼠标归一化 -1~1
  let cx = 0, cy = 0;             // 相机平滑值
  let visible = true, inView = true;

  window.addEventListener("pointermove", (e) => {
    mx = (e.clientX / window.innerWidth) * 2 - 1;
    my = (e.clientY / window.innerHeight) * 2 - 1;
  }, { passive: true });

  document.addEventListener("visibilitychange", () => { visible = !document.hidden; });
  new IntersectionObserver((en) => { inView = en[0].isIntersecting; })
    .observe(canvas);

  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.floor(w * DPR) || canvas.height !== Math.floor(h * DPR)) {
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }
  }
  window.addEventListener("resize", resize, { passive: true });

  const waterMat = scene.getObjectByName("water").material;
  const clock = new THREE.Clock();

  function frame() {
    requestAnimationFrame(frame);
    if (!visible || !inView) return;   // 不在视野内不烧 GPU
    resize();
    const t = clock.getElapsedTime();

    sky.rotation.y = t * 0.018;                      // 星野极缓自转
    cx += (mx * 6 - cx) * 0.04;                      // 视角随指针缓动
    cy += (-my * 3 - cy) * 0.04;
    camera.position.x = cx;
    camera.position.y = 10 + cy;
    camera.lookAt(0, 3, 0);

    for (const pts of [tg36, ds72, tg36r, ds72r]) {
      pts.material.uniforms.uTime.value = t;
    }
    waterMat.uniforms.uTime.value = t;
    renderer.render(scene, camera);
  }

  if (reduceMotion) {
    // 尊重系统减弱动态设置：只渲染一帧静态星野
    sky.rotation.y = 0.6;
    resize();
    renderer.render(scene, camera);
  } else {
    frame();
  }
}
