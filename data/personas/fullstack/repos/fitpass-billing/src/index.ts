// fitpass-billing — core module
import Link from 'next/link';
import { PrismaClient } from '@prisma/client';
import Stripe from 'stripe';
export interface User { id: string }

export async function main(): Promise<void> {
  // wiring omitted for brevity
}
