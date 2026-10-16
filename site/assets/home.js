/* ==========================================================================
   水浒维基 · 首页「排座次」粒子长片（全站 JS 例外之二，design.md §5.21）
   --------------------------------------------------------------------------
   一部由滚动驱动的发布片，一个 Points 缓冲演完全场：
     幕〇「墨」  6000 粒墨云翻涌
     幕壹「字」  墨聚成「水浒」两个粒子大字（895,259 字之形）
     幕贰「星」  字散为星：天罡 36（朱砂）· 地煞 72（月白）
     幕叁「网」  星落为人：159 位人物 · 150 条真实关系边 · 21 个山头阵营
     幕肆「澜」  人散为波：水泊 6000 点波面（55 幕名场面 · 54 条因果边）
     幕伍「归」  波平为镜：入口按钮与回目
   数据（天罡地煞名单、山头阵营成员、150 条关系边）由构建期注入
   <script id="shihu-data">，粒子所见即真实标注数据，无一虚构。
   性能：全部动画在 GPU（uTime/uMix uniform + 属性插值），CPU 每帧只做
   相机缓动；切后台 / 滚离影片区 / prefers-reduced-motion 即停帧。
   ========================================================================== */

import * as THREE from "./vendor/three.module.min.js";

const canvas = document.getElementById("film-canvas");
if (canvas) boot(canvas);

function boot(canvas) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas, antialias: true, alpha: false, powerPreference: "high-performance",
    });
  } catch (e) {
    document.body.classList.add("no-webgl");
    canvas.remove();
    return;
  }

  const DPR = Math.min(window.devicePixelRatio || 1, 2);
  renderer.setPixelRatio(DPR);
  renderer.setClearColor(0x0d0b09, 1);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 800);

  // ---------------------------------------------------------- 数据（构建期注入）
  const dataEl = document.getElementById("shihu-data");
  const DATA = dataEl ? JSON.parse(dataEl.textContent) : { tg: [], ds: [], factions: [], edges: [] };

  const N = 6000;
  const CINK   = new THREE.Color(0x8b8171);  // 墨灰
  const CCIN   = new THREE.Color(0xd4573f);  // 朱砂（暗场提亮）
  const CMOON  = new THREE.Color(0xcfd8dc);  // 月白（黛蓝冷调）
  const CGOLD  = new THREE.Color(0xc9a44a);  // 金
  const CDAI   = new THREE.Color(0x6b96b5);  // 黛蓝波光（暗场提亮）

  // ---------------------------------------------------------- 形态生成器
  // 每个形态给出 N 粒子的 {pos, col, size}
  function blankFormation() {
    return {
      pos: new Float32Array(N * 3),
      col: new Float32Array(N * 3),
      size: new Float32Array(N),
    };
  }
  function setP(f, i, x, y, z, c, s) {
    f.pos[i * 3] = x; f.pos[i * 3 + 1] = y; f.pos[i * 3 + 2] = z;
    f.col[i * 3] = c.r; f.col[i * 3 + 1] = c.g; f.col[i * 3 + 2] = c.b;
    f.size[i] = s;
  }

  // 幕〇 墨云：压扁的椭球浓云，中心厚、边缘散
  function fCloud() {
    const f = blankFormation();
    for (let i = 0; i < N; i++) {
      const r = 46 * Math.pow(Math.random(), 0.5);
      const th = Math.random() * Math.PI * 2;
      const ph = Math.acos(2 * Math.random() - 1);
      const squash = 0.55;
      setP(f, i,
        r * Math.sin(ph) * Math.cos(th),
        r * Math.cos(ph) * squash,
        r * Math.sin(ph) * Math.sin(th),
        CINK, 1.2 + Math.random() * 2.2);
    }
    return f;
  }

  // 幕壹「水浒」粒子字：离屏 canvas 采样字形
  function fText() {
    const f = blankFormation();
    const cw = 960, ch = 480;
    const cv = document.createElement("canvas");
    cv.width = cw; cv.height = ch;
    const ctx = cv.getContext("2d");
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, cw, ch);
    ctx.fillStyle = "#fff";
    ctx.font = '700 330px "Songti SC", "STSong", serif';
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("水浒", cw / 2, ch / 2 + 10);
    const img = ctx.getImageData(0, 0, cw, ch).data;

    const pts = [];
    const step = 3;
    for (let y = 0; y < ch; y += step) {
      for (let x = 0; x < cw; x += step) {
        if (img[(y * cw + x) * 4] > 120) pts.push([x, y]);
      }
    }
    // 洗牌后取样，字形粒子用足 N 的大半
    for (let i = pts.length - 1; i > 0; i--) {
      const j = (Math.random() * (i + 1)) | 0;
      [pts[i], pts[j]] = [pts[j], pts[i]];
    }
    const scale = 0.085;   // 字形映射到世界坐标
    const nText = Math.min(pts.length, 4600);
    for (let i = 0; i < N; i++) {
      if (i < nText) {
        const [x, y] = pts[i];
        setP(f, i,
          (x - cw / 2) * scale,
          (ch / 2 - y) * scale,
          (Math.random() - 0.5) * 2.2,
          Math.random() < 0.06 ? CCIN : CGOLD,   // 6% 朱砂碎金
          1.6 + Math.random() * 1.6);
      } else {
        // 余者作环绕墨尘
        const r = 55 + Math.random() * 40;
        const th = Math.random() * Math.PI * 2;
        setP(f, i, Math.cos(th) * r, (Math.random() - 0.5) * 50, Math.sin(th) * r,
          CINK, 1.0 + Math.random() * 1.2);
      }
    }
    return f;
  }

  // 幕贰 星宿：前 36 天罡（朱砂内圈大星）+ 次 72 地煞（月白外圈）+ 银河带
  function fStars() {
    const f = blankFormation();
    const place = (i, rMin, rMax, c, sMin, sMax) => {
      const th = Math.random() * Math.PI * 2;
      const yN = 0.15 + 0.85 * Math.random();
      const r = rMin + Math.random() * (rMax - rMin);
      const ring = Math.sqrt(Math.max(0, 1 - yN * yN));
      setP(f, i, Math.cos(th) * ring * r, yN * r * 0.7, Math.sin(th) * ring * r,
        c, sMin + Math.random() * (sMax - sMin));
    };
    for (let i = 0; i < 36; i++) place(i, 22, 38, CCIN, 9, 13);          // 天罡
    for (let i = 36; i < 108; i++) place(i, 36, 60, CMOON, 5, 8);        // 地煞
    for (let i = 108; i < N; i++) {                                      // 银河尘带
      const th = Math.random() * Math.PI * 2;
      const r = 70 + Math.random() * 90;
      const y = (Math.random() - 0.35) * 36;
      setP(f, i, Math.cos(th) * r, y, Math.sin(th) * r, CINK, 1.2 + Math.random() * 1.4);
    }
    return f;
  }

  // 幕叁 关系网：159 节点按山头聚簇于球面，边由真实 links 织出
  const graph = { nodePos: new Map(), edges: [] };
  function fGraph() {
    const f = blankFormation();
    const people = [];   // 有序名单：先 108 将（天罡→地煞）后其他
    const all = [...DATA.tg, ...DATA.ds, ...DATA.others];
    for (const n of all) if (!people.includes(n)) people.push(n);

    // 山头簇心：斐波那契球面分布
    const groups = DATA.factions.filter(g => g.members.length);
    const centers = new Map();
    const R = 34;
    groups.forEach((g, gi) => {
      const k = gi + 0.5;
      const ph = Math.acos(1 - 2 * k / groups.length);
      const th = Math.PI * (1 + Math.sqrt(5)) * k;
      centers.set(g.name, [
        R * Math.sin(ph) * Math.cos(th),
        R * Math.cos(ph),
        R * Math.sin(ph) * Math.sin(th),
      ]);
    });

    let idx = 0;
    const heroSet = new Set([...DATA.tg, ...DATA.ds]);
    for (const name of people) {
      let center = null;
      for (const g of groups) {
        if (g.members.includes(name)) { center = centers.get(g.name); break; }
      }
      let x, y, z;
      if (center) {
        x = center[0] + (Math.random() - 0.5) * 11;
        y = center[1] + (Math.random() - 0.5) * 11;
        z = center[2] + (Math.random() - 0.5) * 11;
      } else {
        // 无山头者浮于球壳外层
        const th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
        const rr = R + 10 + Math.random() * 8;
        x = rr * Math.sin(ph) * Math.cos(th);
        y = rr * Math.cos(ph);
        z = rr * Math.sin(ph) * Math.sin(th);
      }
      graph.nodePos.set(name, [x, y, z]);
      const isHero = heroSet.has(name);
      setP(f, idx, x, y, z, isHero ? CCIN : CMOON, isHero ? 3.4 : 2.2);
      idx++;
    }
    // 余者散作背景尘
    for (; idx < N; idx++) {
      const th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
      const rr = 90 + Math.random() * 70;
      setP(f, idx, rr * Math.sin(ph) * Math.cos(th), rr * Math.cos(ph) * 0.6,
        rr * Math.sin(ph) * Math.sin(th), CINK, 0.8 + Math.random());
    }
    // 真实边
    for (const [a, b] of DATA.edges) {
      const pa = graph.nodePos.get(a), pb = graph.nodePos.get(b);
      if (pa && pb) graph.edges.push([...pa, ...pb]);
    }
    return f;
  }

  // 幕肆 水泊：6000 点波面
  function fWater() {
    const f = blankFormation();
    const side = Math.ceil(Math.sqrt(N));
    const SPAN = 220;
    for (let i = 0; i < N; i++) {
      const ix = i % side, iz = (i / side) | 0;
      setP(f, i,
        (ix / (side - 1) - 0.5) * SPAN,
        0,
        (iz / (side - 1) - 0.5) * SPAN,
        CDAI, 2.2 + Math.random() * 1.8);
    }
    return f;
  }

  const formations = [fCloud(), fText(), fStars(), fGraph(), fWater(), fCloud()];

  // ---------------------------------------------------------- 粒子系统（单缓冲双形态插值）
  const geo = new THREE.BufferGeometry();
  const aFrom = new THREE.BufferAttribute(new Float32Array(N * 3), 3);
  const aTo = new THREE.BufferAttribute(new Float32Array(N * 3), 3);
  const aColFrom = new THREE.BufferAttribute(new Float32Array(N * 3), 3);
  const aColTo = new THREE.BufferAttribute(new Float32Array(N * 3), 3);
  const aSizeFrom = new THREE.BufferAttribute(new Float32Array(N), 1);
  const aSizeTo = new THREE.BufferAttribute(new Float32Array(N), 1);
  const aSeed = new THREE.BufferAttribute(new Float32Array(N), 1);
  for (let i = 0; i < N; i++) aSeed.setX(i, Math.random() * Math.PI * 2);
  geo.setAttribute("position", aFrom);   // position 占位（实际用 aFrom/aTo 插值）
  geo.setAttribute("aFrom", aFrom);
  geo.setAttribute("aTo", aTo);
  geo.setAttribute("aColFrom", aColFrom);
  geo.setAttribute("aColTo", aColTo);
  geo.setAttribute("aSizeFrom", aSizeFrom);
  geo.setAttribute("aSizeTo", aSizeTo);
  geo.setAttribute("aSeed", aSeed);

  const uniforms = {
    uTime: { value: 0 },
    uMix: { value: 0 },
    uWave: { value: 0 },          // 波面振幅权重（幕肆拉满）
    uDpr: { value: DPR },
  };

  const mat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms,
    vertexShader: /* glsl */`
      attribute vec3 aFrom, aTo, aColFrom, aColTo;
      attribute float aSizeFrom, aSizeTo, aSeed;
      uniform float uTime, uMix, uWave, uDpr;
      varying vec3 vCol;
      varying float vTw;
      void main() {
        float m = uMix;
        // easeInOutCubic 在 GPU 端做，CPU 只推 uMix 线性值
        m = m < 0.5 ? 4.0*m*m*m : 1.0 - pow(-2.0*m + 2.0, 3.0) / 2.0;
        vec3 p = mix(aFrom, aTo, m);
        // 全局微漂 + 幕肆波面起伏（y 原本为 0 的点被 uWave 驱动）
        p.x += sin(uTime * 0.5 + aSeed) * 0.35;
        p.y += cos(uTime * 0.4 + aSeed * 1.7) * 0.3;
        float wave = sin(uTime * 1.2 + p.x * 0.09 + p.z * 0.07)
                   * cos(uTime * 0.8 + p.z * 0.11);
        p.y += wave * 2.2 * uWave;
        vCol = mix(aColFrom, aColTo, m);
        vTw = 0.68 + 0.32 * sin(uTime * (0.7 + fract(aSeed) * 0.9) + aSeed);
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        gl_Position = projectionMatrix * mv;
        float sz = mix(aSizeFrom, aSizeTo, m);
        gl_PointSize = sz * uDpr * vTw * (170.0 / -mv.z);
      }
    `,
    fragmentShader: /* glsl */`
      varying vec3 vCol;
      varying float vTw;
      void main() {
        vec2 uv = gl_PointCoord - 0.5;
        float d = length(uv);
        float glow = smoothstep(0.5, 0.0, d);
        float core = smoothstep(0.16, 0.0, d);
        float a = (glow * 0.5 + core * 0.85) * vTw;
        if (a < 0.015) discard;
        gl_FragColor = vec4(vCol, a);
      }
    `,
  });
  scene.add(new THREE.Points(geo, mat));

  // ---------------------------------------------------------- 关系边（幕叁淡入）
  let lineMat = null;
  if (graph.edges.length) {
    const lg = new THREE.BufferGeometry();
    lg.setAttribute("position", new THREE.Float32BufferAttribute(graph.edges.flat(), 3));
    lineMat = new THREE.LineBasicMaterial({
      color: 0x9a6a55, transparent: true, opacity: 0,
      blending: THREE.AdditiveBlending, depthWrite: false,
    });
    scene.add(new THREE.LineSegments(lg, lineMat));
  }

  // ---------------------------------------------------------- 形态切换
  let curForm = 0;
  let mixStart = -1, mixFrom = 0, mixTarget = 0;
  const MIX_MS = 1700;

  function loadForm(attrs, f) {
    attrs.pos.set(f.pos); attrs.col.set(f.col); attrs.size.set(f.size);
  }
  function applyToAttributes(f, toPos, toCol, toSize) {
    toPos.array.set(f.pos); toPos.needsUpdate = true;
    toCol.array.set(f.col); toCol.needsUpdate = true;
    toSize.array.set(f.size); toSize.needsUpdate = true;
  }
  function morphTo(idx) {
    if (idx === curForm) return;
    // 当前形态 = 混合中值或目标形态；简化：总是从「上一个目标」出发
    applyToAttributes(formations[curForm], aFrom, aColFrom, aSizeFrom);
    applyToAttributes(formations[idx], aTo, aColTo, aSizeTo);
    aFrom.needsUpdate = aColFrom.needsUpdate = aSizeFrom.needsUpdate = true;
    curForm = idx;
    mixFrom = 0; mixTarget = 1; mixStart = performance.now();
    uniforms.uMix.value = 0;
  }
  // 初始化为幕〇
  applyToAttributes(formations[0], aFrom, aColFrom, aSizeFrom);
  applyToAttributes(formations[0], aTo, aColTo, aSizeTo);
  uniforms.uMix.value = 1;

  // ---------------------------------------------------------- 相机关键帧（每幕一机位）
  const CAM = [
    { pos: [0, 2, 95],  look: [0, 0, 0] },    // 幕〇 墨云平视
    { pos: [0, 0, 62],  look: [0, 0, 0] },    // 幕壹 正面大字
    { pos: [0, 10, 68], look: [0, 8, 0] },    // 幕贰 仰观星野
    { pos: [38, 18, 70], look: [0, 0, 0] },   // 幕叁 侧瞰关系球
    { pos: [0, 26, 62], look: [0, -4, 0] },   // 幕肆 俯望水泊
    { pos: [0, 6, 110], look: [0, 0, 0] },    // 幕伍 拉远收官
  ];
  let camPos = new THREE.Vector3(...CAM[0].pos);
  let camLook = new THREE.Vector3(...CAM[0].look);
  let camTargetPos = new THREE.Vector3(...CAM[0].pos);
  let camTargetLook = new THREE.Vector3(...CAM[0].look);
  let waveTarget = 0, lineTarget = 0;

  // ---------------------------------------------------------- 滚动驱动
  const acts = Array.from(document.querySelectorAll(".act"));
  const film = document.getElementById("film");
  let activeAct = -1, filmInView = true;

  function onScroll() {
    if (!film) return;
    const y = window.scrollY;
    const vh = window.innerHeight;
    const top = film.offsetTop;
    let idx = 0;
    acts.forEach((a, i) => {
      if (y >= top + a.offsetTop - vh * 0.5) idx = i;
    });
    filmInView = y < top + film.offsetHeight - vh * 0.4;
    document.body.classList.toggle("past-film", !filmInView);
    if (idx !== activeAct) {
      activeAct = idx;
      morphTo(Math.min(idx, formations.length - 1));
      const c = CAM[Math.min(idx, CAM.length - 1)];
      camTargetPos.set(...c.pos);
      camTargetLook.set(...c.look);
      waveTarget = idx === 4 ? 1 : 0;
      lineTarget = idx === 3 ? 0.55 : 0;
      document.body.dataset.act = String(idx);
    }
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // 调试/深链：?act=N 直达第 N 幕（0 起），瞬时就位不播过渡
  const forceAct = new URLSearchParams(location.search).get("act");
  if (forceAct !== null && acts[+forceAct]) {
    const i = +forceAct;
    const fi = Math.min(i, formations.length - 1);
    applyToAttributes(formations[fi], aFrom, aColFrom, aSizeFrom);
    applyToAttributes(formations[fi], aTo, aColTo, aSizeTo);
    aFrom.needsUpdate = aColFrom.needsUpdate = aSizeFrom.needsUpdate = true;
    uniforms.uMix.value = 1;
    curForm = fi; activeAct = i;
    const c = CAM[Math.min(i, CAM.length - 1)];
    camPos.set(...c.pos); camLook.set(...c.look);
    camTargetPos.set(...c.pos); camTargetLook.set(...c.look);
    waveTarget = i === 4 ? 1 : 0;
    lineTarget = i === 3 ? 0.55 : 0;
    uniforms.uWave.value = waveTarget;
    if (lineMat) lineMat.opacity = lineTarget;
    document.body.dataset.act = String(i);
  }

  // 鼠标视差
  let mx = 0, my = 0;
  window.addEventListener("pointermove", (e) => {
    mx = (e.clientX / window.innerWidth) * 2 - 1;
    my = (e.clientY / window.innerHeight) * 2 - 1;
  }, { passive: true });

  function resize() {
    const w = window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize, { passive: true });
  resize();

  let pageVisible = true;
  document.addEventListener("visibilitychange", () => { pageVisible = !document.hidden; });

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clock = new THREE.Clock();

  function frame() {
    requestAnimationFrame(frame);
    if (!pageVisible || !filmInView) return;
    const t = clock.getElapsedTime();
    uniforms.uTime.value = t;

    // 形态混合进度
    if (mixStart >= 0) {
      const k = Math.min(1, (performance.now() - mixStart) / MIX_MS);
      uniforms.uMix.value = mixFrom + (mixTarget - mixFrom) * k;
      if (k >= 1) mixStart = -1;
    }
    // 波幅与边线缓动
    uniforms.uWave.value += (waveTarget - uniforms.uWave.value) * 0.03;
    if (lineMat) lineMat.opacity += (lineTarget - lineMat.opacity) * 0.04;

    // 相机缓动 + 视差
    camPos.lerp(camTargetPos, 0.045);
    camLook.lerp(camTargetLook, 0.045);
    camera.position.set(camPos.x + mx * 5, camPos.y - my * 3, camPos.z);
    camera.lookAt(camLook);

    // 幕叁关系球缓缓自转
    scene.rotation.y = activeAct === 3 ? t * 0.05 : scene.rotation.y * 0.99;

    renderer.render(scene, camera);
  }

  if (reduceMotion) {
    uniforms.uMix.value = 1;
    camera.position.set(...CAM[0].pos);
    camera.lookAt(...CAM[0].look);
    renderer.render(scene, camera);
  } else {
    frame();
  }
}
