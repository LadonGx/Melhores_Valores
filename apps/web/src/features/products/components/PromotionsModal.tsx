import { Modal } from '@/components/Modal';
import type { ProductPromotion } from '@mv/types';
import { formatCurrency, formatStore } from '@mv/utils';
import detailStyles from './ProductDetailModal.module.css';
import styles from './PromotionsModal.module.css';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  promotions: ProductPromotion[];
}

export function PromotionsModal({ isOpen, onClose, promotions }: Props) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Produtos em promoção hoje" size="lg">
      <div className={styles.list}>
        {promotions.map((promo) => (
          <div key={promo.id} className={styles.row}>
            {promo.image_url ? (
              <img src={promo.image_url} alt="" className={styles.thumb} loading="lazy" />
            ) : (
              <div className={styles.thumbPlaceholder} />
            )}

            <div className={styles.info}>
              <span className={detailStyles.storeBadge}>{formatStore(promo.store)}</span>
              <span className={styles.name}>{promo.name ?? promo.url}</span>
            </div>

            <div className={styles.priceInfo}>
              <span className={styles.previousPrice}>
                {formatCurrency(promo.previous_lowest_price)}
              </span>
              <span className={`${detailStyles.price} ${detailStyles.priceLowest}`}>
                {formatCurrency(promo.current_price)}
              </span>
              <span className={styles.savings}>
                -{formatCurrency(promo.savings)}
              </span>
            </div>

            <a href={promo.url} target="_blank" rel="noreferrer" className={styles.buyLink}>
              Ver anúncio →
            </a>
          </div>
        ))}
      </div>
    </Modal>
  );
}
