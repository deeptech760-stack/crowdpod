"use client";
import { useEffect, type ReactNode } from "react";
import { MotionConfig } from "motion/react";
import Lenis from "lenis";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
gsap.registerPlugin(ScrollTrigger);
export default function MotionProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    const media = gsap.matchMedia();
    media.add("(prefers-reduced-motion: no-preference)", () => {
      const lenis = new Lenis({
        duration: 1.05,
        smoothWheel: true,
        anchors: { offset: -95 },
      });
      lenis.on("scroll", ScrollTrigger.update);
      const tick = (time: number) => lenis.raf(time * 1000);
      gsap.ticker.add(tick);
      gsap.utils.toArray<HTMLElement>("[data-reveal]").forEach((el) => {
        gsap.from(el, {
          y: 35,
          opacity: 0,
          duration: 0.9,
          ease: "power3.out",
          scrollTrigger: { trigger: el, start: "top 93%", once: true },
        });
      });
      gsap.to(".scroll-progress", {
        scaleX: 1,
        ease: "none",
        scrollTrigger: { start: 0, end: "max", scrub: true },
      });
      gsap.fromTo(
        ".final-ghost",
        { y: 70, rotate: 8 },
        {
          y: 0,
          rotate: 0,
          scrollTrigger: {
            trigger: ".final-cta",
            start: "top bottom",
            end: "bottom bottom",
            scrub: 1,
          },
        },
      );
      gsap.to(".final-fragment-one", {
        x: 90,
        y: -35,
        opacity: 0.2,
        scrollTrigger: {
          trigger: ".final-cta",
          start: "top 70%",
          end: "bottom bottom",
          scrub: 1,
        },
      });
      gsap.to(".final-fragment-two", {
        x: 35,
        y: 80,
        opacity: 0.15,
        scrollTrigger: {
          trigger: ".final-cta",
          start: "top 70%",
          end: "bottom bottom",
          scrub: 1,
        },
      });
      return () => {
        gsap.ticker.remove(tick);
        lenis.destroy();
      };
    });
    return () => media.revert();
  }, []);
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
