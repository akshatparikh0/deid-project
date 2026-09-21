import type { Category } from '@/api/types';
import { categoryColor, categoryLabel } from '@/lib/categories';

export function CategoryDot({ category }: { category: Category }) {
  return <span className="badge-dot" style={{ background: categoryColor(category) }} />;
}

export function CategoryBadge({ category }: { category: Category }) {
  return (
    <span className="badge category-badge">
      <CategoryDot category={category} />
      {categoryLabel(category)}
    </span>
  );
}
