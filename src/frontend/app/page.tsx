import Navbar from "@/components/landing/Navbar";
import Hero from "@/components/landing/Hero";
import CrewSection from "@/components/landing/CrewSection";
import PipelineSection from "@/components/landing/PipelineSection";
import ObservationDeckPreview from "@/components/landing/ObservationDeckPreview";
import Footer from "@/components/landing/Footer";

export default function HomePage() {
  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <CrewSection />
        <PipelineSection />
        <ObservationDeckPreview />
      </main>
      <Footer />
    </>
  );
}
