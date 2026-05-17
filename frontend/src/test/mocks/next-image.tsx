import React from "react";

type StaticImageData = { src: string; width: number; height: number; blurDataURL?: string };

const Image = ({
  src,
  alt,
  width,
  height,
  className,
}: {
  src: string | StaticImageData;
  alt: string;
  width?: number;
  height?: number;
  className?: string;
  priority?: boolean;
  [key: string]: unknown;
}) => {
  const resolvedSrc = typeof src === "object" ? src.src : src;
  const resolvedWidth = width ?? (typeof src === "object" ? src.width : undefined);
  const resolvedHeight = height ?? (typeof src === "object" ? src.height : undefined);
  return (
    <img
      src={resolvedSrc}
      alt={alt}
      width={resolvedWidth}
      height={resolvedHeight}
      className={className}
    />
  );
};

export default Image;
