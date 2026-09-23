import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { paths } from '@/config/paths';

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-start gap-3 py-16">
      <span className="text-muted-foreground font-mono text-xs">404</span>
      <h1 className="font-serif text-[26px]">Page not found</h1>
      <p className="text-muted-foreground text-[13.5px]">
        The page you're looking for doesn't exist or may have moved.
      </p>
      <Button asChild size="sm" className="mt-1">
        <Link to={paths.queue.getHref()}>Back to document library</Link>
      </Button>
    </div>
  );
}
