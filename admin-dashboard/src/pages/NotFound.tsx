import { useNavigate } from 'react-router-dom';
import { Compass } from 'lucide-react';
import { Button, Card } from '@/components/ui/primitives';

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="max-w-md p-8 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-elevated text-faint">
          <Compass className="h-5 w-5" />
        </div>
        <h2 className="mt-4 text-lg font-semibold text-ink">Page not found</h2>
        <p className="mt-1 text-sm text-muted">
          The section you are looking for does not exist or has moved.
        </p>
        <Button className="mt-5" onClick={() => navigate('/')}>
          Back to dashboard
        </Button>
      </Card>
    </div>
  );
}
