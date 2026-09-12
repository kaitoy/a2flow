import {useRef} from 'react';
import type {ComponentProps, ReactNode} from 'react';
import {createPortal} from 'react-dom';
import clsx from 'clsx';
import useIsBrowser from '@docusaurus/useIsBrowser';

import styles from './styles.module.css';

/** Props for {@link MDXImg} — whatever attributes a Markdown `![]()` image carries. */
type Props = ComponentProps<'img'>;

/**
 * Renders Markdown images the way `@docusaurus/theme-classic` does (lazy,
 * `height: auto`), plus a click-to-zoom escape hatch: every image opens
 * enlarged in a native `<dialog>`, closable via Escape, a backdrop click, or
 * clicking the enlarged image itself. The manual's diagrams pack small type
 * that doesn't survive the doc column's width, so this applies everywhere
 * without any per-page markup change.
 *
 * The dialog is portaled into `document.body`: Markdown wraps a standalone
 * image in a `<p>`, and `<dialog>` isn't valid phrasing content there, so
 * rendering it as a sibling of the image would leave invalid, mis-nested
 * HTML in the page. `useIsBrowser` keeps it out of the static/SSR output
 * entirely, since `document` doesn't exist at build time.
 */
export default function MDXImg(props: Props): ReactNode {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const isBrowser = useIsBrowser();

  const dialog = (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      onClick={(event) => {
        if (event.target === dialogRef.current) {
          dialogRef.current?.close();
        }
      }}>
      <img
        src={props.src}
        alt={props.alt}
        width={props.width}
        height={props.height}
        className={styles.zoomedImg}
        onClick={() => dialogRef.current?.close()}
      />
    </dialog>
  );

  return (
    <>
      <button type="button" className={styles.trigger} onClick={() => dialogRef.current?.showModal()}>
        <img decoding="async" loading="lazy" {...props} className={clsx(props.className, styles.img)} />
      </button>
      {isBrowser && createPortal(dialog, document.body)}
    </>
  );
}
