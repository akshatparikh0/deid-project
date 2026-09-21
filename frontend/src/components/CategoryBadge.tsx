import type { Category } from '@/api/types';
import { Badge } from '@/components/ui/badge';
import { categoryColor, categoryLabel } from '@/lib/categories';

export function CategoryDot({ category }: { category: Category }) {
  return <span className="size-1.75 shrink-0 rounded-full" style={{ background: categoryColor(category) }} />;
}

export function CategoryBadge({ category }: { category: Category }) {
  return (
    <Badge variant="outline" className="bg-secondary text-secondary-foreground gap-1.5 border-transparent">
      <CategoryDot category={category} />
      {categoryLabel(category)}
    </Badge>
  );
}
