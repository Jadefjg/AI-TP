<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  pulse: number;
  pulseSpeed: number;
};

const canvasRef = ref<HTMLCanvasElement | null>(null);
let frameId = 0;
let particles: Particle[] = [];
let width = 0;
let height = 0;
let mouseX = -9999;
let mouseY = -9999;
let time = 0;

const PARTICLE_COUNT = 110;
const LINK_DISTANCE = 155;
const MOUSE_RADIUS = 200;

function rand(min: number, max: number) {
  return min + Math.random() * (max - min);
}

function initParticles() {
  particles = Array.from({ length: PARTICLE_COUNT }, () => ({
    x: rand(0, width),
    y: rand(0, height),
    vx: rand(-0.28, 0.28),
    vy: rand(-0.28, 0.28),
    radius: rand(1, 2.2),
    pulse: rand(0, Math.PI * 2),
    pulseSpeed: rand(0.015, 0.035),
  }));
}

function resize() {
  const canvas = canvasRef.value;
  if (!canvas) return;
  width = window.innerWidth;
  height = window.innerHeight;
  canvas.width = width;
  canvas.height = height;
  if (!particles.length) initParticles();
}

function drawAurora(ctx: CanvasRenderingContext2D) {
  const bands = [
    { y: height * 0.18, amp: 42, color: "rgba(34, 211, 238, 0.07)" },
    { y: height * 0.32, amp: 56, color: "rgba(139, 92, 246, 0.06)" },
    { y: height * 0.48, amp: 38, color: "rgba(59, 130, 246, 0.05)" },
  ];

  for (const band of bands) {
    ctx.beginPath();
    ctx.moveTo(0, band.y);
    for (let x = 0; x <= width; x += 12) {
      const y =
        band.y +
        Math.sin(x * 0.004 + time * 0.0012) * band.amp +
        Math.cos(x * 0.009 - time * 0.0008) * (band.amp * 0.45);
      ctx.lineTo(x, y);
    }
    ctx.lineTo(width, 0);
    ctx.lineTo(0, 0);
    ctx.closePath();
    ctx.fillStyle = band.color;
    ctx.fill();
  }
}

function draw(ctx: CanvasRenderingContext2D) {
  ctx.clearRect(0, 0, width, height);
  drawAurora(ctx);

  for (const p of particles) {
    p.pulse += p.pulseSpeed;
    p.x += p.vx;
    p.y += p.vy;
    if (p.x < 0 || p.x > width) p.vx *= -1;
    if (p.y < 0 || p.y > height) p.vy *= -1;

    const dxm = mouseX - p.x;
    const dym = mouseY - p.y;
    const distMouse = Math.hypot(dxm, dym);
    if (distMouse < MOUSE_RADIUS && distMouse > 0) {
      const force = (MOUSE_RADIUS - distMouse) / MOUSE_RADIUS;
      p.x -= (dxm / distMouse) * force * 0.75;
      p.y -= (dym / distMouse) * force * 0.75;
    }
  }

  for (let i = 0; i < particles.length; i += 1) {
    for (let j = i + 1; j < particles.length; j += 1) {
      const a = particles[i];
      const b = particles[j];
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const dist = Math.hypot(dx, dy);
      if (dist > LINK_DISTANCE) continue;

      const alpha = (1 - dist / LINK_DISTANCE) * 0.38;
      const gradient = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
      gradient.addColorStop(0, `rgba(56, 189, 248, ${alpha})`);
      gradient.addColorStop(0.5, `rgba(167, 139, 250, ${alpha * 0.9})`);
      gradient.addColorStop(1, `rgba(99, 102, 241, ${alpha})`);
      ctx.strokeStyle = gradient;
      ctx.lineWidth = 0.85;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
  }

  for (const p of particles) {
    const glowSize = p.radius * (3.5 + Math.sin(p.pulse) * 1.2);
    const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, glowSize * 3);
    glow.addColorStop(0, `rgba(125, 211, 252, ${0.55 + Math.sin(p.pulse) * 0.2})`);
    glow.addColorStop(1, "rgba(125, 211, 252, 0)");
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(p.x, p.y, glowSize * 3, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "rgba(224, 242, 254, 0.92)";
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
    ctx.fill();
  }
}

function tick() {
  const canvas = canvasRef.value;
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  time += 1;
  draw(ctx);
  frameId = window.requestAnimationFrame(tick);
}

function onMouseMove(event: MouseEvent) {
  mouseX = event.clientX;
  mouseY = event.clientY;
}

function onMouseLeave() {
  mouseX = -9999;
  mouseY = -9999;
}

onMounted(() => {
  resize();
  window.addEventListener("resize", resize);
  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseleave", onMouseLeave);
  frameId = window.requestAnimationFrame(tick);
});

onUnmounted(() => {
  window.cancelAnimationFrame(frameId);
  window.removeEventListener("resize", resize);
  window.removeEventListener("mousemove", onMouseMove);
  window.removeEventListener("mouseleave", onMouseLeave);
});
</script>

<template>
  <div class="login-bg" aria-hidden="true">
    <div class="login-bg__base" />
    <div class="login-bg__hex" />
    <div class="login-bg__grid" />
    <div class="login-bg__ring" />
    <div class="login-bg__beam" />
    <div class="login-bg__scanline" />
    <div class="login-bg__orb login-bg__orb--cyan" />
    <div class="login-bg__orb login-bg__orb--violet" />
    <div class="login-bg__orb login-bg__orb--blue" />
    <div class="login-bg__orb login-bg__orb--indigo" />
    <canvas ref="canvasRef" class="login-bg__canvas" />
    <div class="login-bg__noise" />
    <div class="login-bg__vignette" />
  </div>
</template>

<style scoped>
.login-bg {
  position: fixed;
  inset: 0;
  overflow: hidden;
  z-index: 0;
  background: #010409;
}

.login-bg__base {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 90% 60% at 10% 15%, rgba(6, 182, 212, 0.18), transparent 55%),
    radial-gradient(ellipse 80% 55% at 92% 78%, rgba(124, 58, 237, 0.16), transparent 58%),
    radial-gradient(ellipse 55% 40% at 50% 110%, rgba(37, 99, 235, 0.12), transparent 52%),
    radial-gradient(circle at 50% 50%, rgba(15, 23, 42, 0.4), transparent 70%),
    linear-gradient(165deg, #010409 0%, #050b18 38%, #0a1020 68%, #060a14 100%);
}

.login-bg__hex {
  position: absolute;
  inset: 0;
  opacity: 0.04;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='56' height='100' viewBox='0 0 56 100'%3E%3Cpath d='M28 0L56 16v32L28 64 0 48V16z' fill='none' stroke='%2338bdf8' stroke-width='0.6'/%3E%3C/svg%3E");
  background-size: 56px 100px;
  mask-image: radial-gradient(ellipse at center, black 20%, transparent 78%);
}

.login-bg__grid {
  position: absolute;
  inset: -25% -10%;
  background-image:
    linear-gradient(rgba(56, 189, 248, 0.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 189, 248, 0.055) 1px, transparent 1px);
  background-size: 48px 48px;
  transform: perspective(820px) rotateX(72deg) translateY(14%);
  transform-origin: center top;
  mask-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.9), transparent 92%);
  animation: grid-drift 22s linear infinite;
}

.login-bg__ring {
  position: absolute;
  top: 50%;
  left: 50%;
  width: min(90vw, 900px);
  height: min(90vw, 900px);
  transform: translate(-50%, -50%);
  border-radius: 50%;
  border: 1px solid rgba(56, 189, 248, 0.08);
  box-shadow:
    0 0 80px rgba(34, 211, 238, 0.06),
    inset 0 0 80px rgba(139, 92, 246, 0.04);
  animation: ring-spin 48s linear infinite;
}

.login-bg__ring::before,
.login-bg__ring::after {
  content: "";
  position: absolute;
  inset: 18%;
  border-radius: 50%;
  border: 1px dashed rgba(167, 139, 250, 0.12);
}

.login-bg__ring::after {
  inset: 32%;
  border-style: solid;
  border-color: rgba(56, 189, 248, 0.06);
  animation: ring-spin 32s linear infinite reverse;
}

.login-bg__beam {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    105deg,
    transparent 42%,
    rgba(56, 189, 248, 0.04) 49%,
    rgba(167, 139, 250, 0.07) 50%,
    rgba(56, 189, 248, 0.04) 51%,
    transparent 58%
  );
  animation: beam-sweep 9s ease-in-out infinite;
  pointer-events: none;
}

.login-bg__scanline {
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    to bottom,
    rgba(255, 255, 255, 0.012) 0,
    rgba(255, 255, 255, 0.012) 1px,
    transparent 1px,
    transparent 3px
  );
  pointer-events: none;
  opacity: 0.4;
}

.login-bg__orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.5;
  animation: orb-float 14s ease-in-out infinite;
}

.login-bg__orb--cyan {
  width: 480px;
  height: 480px;
  top: -12%;
  left: -8%;
  background: rgba(34, 211, 238, 0.32);
}

.login-bg__orb--violet {
  width: 560px;
  height: 560px;
  right: -12%;
  bottom: -15%;
  background: rgba(139, 92, 246, 0.28);
  animation-delay: -5s;
}

.login-bg__orb--blue {
  width: 320px;
  height: 320px;
  top: 42%;
  left: 55%;
  background: rgba(59, 130, 246, 0.22);
  animation-delay: -8s;
}

.login-bg__orb--indigo {
  width: 240px;
  height: 240px;
  top: 12%;
  right: 18%;
  background: rgba(99, 102, 241, 0.2);
  animation-delay: -3s;
}

.login-bg__canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.login-bg__noise {
  position: absolute;
  inset: 0;
  opacity: 0.045;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  pointer-events: none;
}

.login-bg__vignette {
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at center, transparent 28%, rgba(1, 4, 9, 0.82) 100%);
  pointer-events: none;
}

@keyframes grid-drift {
  from {
    background-position: 0 0;
  }
  to {
    background-position: 0 48px;
  }
}

@keyframes orb-float {
  0%,
  100% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  33% {
    transform: translate3d(12px, -20px, 0) scale(1.06);
  }
  66% {
    transform: translate3d(-8px, 14px, 0) scale(0.98);
  }
}

@keyframes ring-spin {
  from {
    transform: translate(-50%, -50%) rotate(0deg);
  }
  to {
    transform: translate(-50%, -50%) rotate(360deg);
  }
}

@keyframes beam-sweep {
  0%,
  100% {
    transform: translateX(-18%) skewX(-8deg);
    opacity: 0.35;
  }
  50% {
    transform: translateX(18%) skewX(-8deg);
    opacity: 0.85;
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-bg__grid,
  .login-bg__ring,
  .login-bg__ring::after,
  .login-bg__beam,
  .login-bg__orb {
    animation: none;
  }
}
</style>
