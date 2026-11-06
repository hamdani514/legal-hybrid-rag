import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { pageReady } from './lib/bootSkeleton'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

/**
 * Fade out the loading skeleton from index.html.
 *
 * It goes once the routed page has rendered (pages load on demand, so its
 * code may arrive after React starts) AND the web fonts are ready
 * (so the page does not appear in a fallback font and then jump), but never
 * before it has been on screen for SKELETON_MIN_MS: a refresh that finishes
 * in 100 ms would otherwise flash the skeleton for a frame, which reads as a
 * glitch rather than as loading. FONT_WAIT_MAX_MS caps the wait for a slow
 * font server, PAGE_WAIT_MAX_MS a page chunk that never arrives (the page
 * then shows whatever it has, rather than a skeleton forever).
 */
const SKELETON_MIN_MS = 700
const FONT_WAIT_MAX_MS = 1500
const PAGE_WAIT_MAX_MS = 10000

const hideSkeleton = () => {
  const skeleton = document.getElementById('boot-skeleton')
  if (!skeleton) return
  const fontsReady = Promise.race([
    document.fonts?.ready ?? Promise.resolve(),
    new Promise((resolve) => setTimeout(resolve, FONT_WAIT_MAX_MS)),
  ])
  const pageDrawn = Promise.race([
    pageReady,
    new Promise((resolve) => setTimeout(resolve, PAGE_WAIT_MAX_MS)),
  ])
  // performance.now() counts from the start of the page load, so time spent
  // downloading the bundle counts towards the minimum.
  const shownFor = new Promise((resolve) =>
    setTimeout(resolve, Math.max(0, SKELETON_MIN_MS - performance.now())),
  )
  Promise.all([fontsReady, shownFor, pageDrawn]).then(() => {
    // Two frames: the first lets React's commit reach the screen.
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        window.scrollTo(0, 0)
        skeleton.classList.add('boot-done')
        skeleton.addEventListener('transitionend', () => skeleton.remove(), { once: true })
        // In case the transition never fires (tab hidden, reduced motion).
        setTimeout(() => skeleton.remove(), 600)
      }),
    )
  })
}

hideSkeleton()
